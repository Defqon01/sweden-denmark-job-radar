"""
data.json generator — the daily public snapshot consumed by the website.

Produces the JSON contract the front-end fetches:
{
  generated_at, period, summary,
  countries:[{name,code,layoff_level,layoff_score,events,vacancies,headline,headline_url,summary}],
  top_events:[{company,country,type,jobs_affected,title,url,date}],
  rising_skills:[{skill,demand_index,trend,evidence}],
  shortages:[{country,occupation,severity}],
  sources_count
}

Two layers:
1. A deterministic baseline (always works, no API key) that clusters news into
   distinct events — fixing the v1 problem where one layoff covered by many
   outlets inflated a country's score. Country ranking is by DISTINCT EVENTS,
   not article volume.
2. An optional Claude Haiku pass that refines the narrative summary, the event
   clustering / jobs-affected numbers, per-country one-liners, and rising-skill
   labels. Any failure falls back to the deterministic output.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone


def _period_label(days: int) -> str:
    """Human-friendly week range, e.g. 'Week of Jun 6–12, 2026'."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    return f"Week of {start.strftime('%b %d').lstrip('0')}–{end.strftime('%b %d, %Y').lstrip('0')}"

import config
from radar.db import get_recent_items
from radar.reporting import eu_skills
from radar.utils.logging import get_logger

logger = get_logger(__name__)

AGGREGATES = {"Europe", "EU"}
LAYOFF_SIGNALS = {"layoff", "restructuring", "hiring_freeze"}

# Numbers near layoff verbs/nouns → "jobs affected".
_JOBS_NEAR_NOUN = re.compile(
    r"(\d{1,3}(?:[,.]\d{3})+|\d{2,6})\s*"
    r"(?:jobs|positions|roles|employees|workers|staff|posts)",
    re.I,
)
_VERB_NEAR_NUM = re.compile(
    r"(?:cut|lay[\s-]?off|laying off|axe|reduce|reducing|eliminate|slash|"
    r"shed|trim|let go|redundanc\w*)\s+(?:up to\s+|around\s+|nearly\s+|about\s+)?"
    r"(\d{1,3}(?:[,.]\d{3})+|\d{2,6})",
    re.I,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _title_key(title: str | None) -> str:
    words = re.findall(r"\w+", (title or "").lower())
    return " ".join(words[:6])


def _extract_jobs_affected(*texts: str | None) -> int | None:
    """Pull the largest plausible 'jobs affected' number from text, or None."""
    best = 0
    for text in texts:
        if not text:
            continue
        for pat in (_JOBS_NEAR_NOUN, _VERB_NEAR_NUM):
            for m in pat.finditer(text):
                n = int(re.sub(r"[,.]", "", m.group(1)))
                if 10 <= n <= 500_000:  # filter noise (years, tiny counts)
                    best = max(best, n)
    return best or None


def _cluster_layoff_events(items: list[dict]) -> list[dict]:
    """
    Collapse layoff/restructuring articles into DISTINCT events.

    Cluster key = company (if known) else a normalised title prefix. This stops
    one event reported by many outlets from counting multiple times.
    """
    clusters: dict[str, dict] = {}
    for item in items:
        if item.get("signal_type") not in LAYOFF_SIGNALS:
            continue
        company = (item.get("company") or "").strip()
        country = item.get("country")
        title = item.get("title") or ""
        # Key: company+country when we have a company, else title-prefix.
        key = f"{company.lower()}|{country}" if company else _title_key(title)
        jobs = _extract_jobs_affected(title, item.get("summary"))

        c = clusters.get(key)
        if c is None:
            clusters[key] = {
                "company": company or None,
                "country": country,
                "type": item.get("signal_type"),
                "jobs_affected": jobs,
                "title": title,
                "url": item.get("url"),
                "date": (item.get("published_at") or item.get("collected_at") or "")[:10],
                "_count": 1,
            }
        else:
            c["_count"] += 1
            if jobs and (not c["jobs_affected"] or jobs > c["jobs_affected"]):
                c["jobs_affected"] = jobs
            # Prefer a representative title that names a company/number.
            if not c["company"] and company:
                c["company"] = company
    return list(clusters.values())


def _resolve_event_item(ev: dict, items: list[dict]) -> dict | None:
    """Find the real collected article for an LLM event (match company/title)."""
    company = (ev.get("company") or "").lower().strip()
    title_words = set(re.findall(r"\w+", (ev.get("title") or "").lower())[:6])
    fallback = None
    for i in items:
        if not i.get("url"):
            continue
        t = (i.get("title") or "").lower()
        if company and len(company) > 2 and company in t:
            return i
        if title_words and len(title_words & set(re.findall(r"\w+", t))) >= 4:
            fallback = i
    return fallback


def _layoff_level(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "elevated"
    if score >= 0.10:
        return "moderate"
    return "low"


def _rising_skills(items: list[dict], limit: int = 8) -> list[dict]:
    """Aggregate in-demand skills from job-board postings + keyword scan."""
    counter: Counter = Counter()
    job_items = [i for i in items if i.get("signal_type") == "job_posting"]
    # Sector/occupation labels from job boards.
    for i in job_items:
        sector = (i.get("sector") or "").strip()
        if sector:
            counter[sector] += 1
    # Keyword scan across all titles for tech/role themes.
    haystacks = [((i.get("title") or "") + " " + (i.get("summary") or "")).lower()
                 for i in items]
    for kw in config.EXTRA_KEYWORDS_OF_INTEREST:
        pat = re.compile(r"\b" + re.escape(kw.lower()) + r"\b")
        hits = sum(1 for h in haystacks if pat.search(h))
        if hits:
            counter[kw] += hits
    if not counter:
        return []
    top = counter.most_common(limit)
    max_count = top[0][1]
    out = []
    for skill, count in top:
        out.append({
            "skill": skill.title() if skill.islower() else skill,
            "demand_index": max(1, round(count / max_count * 100)),
            "trend": "flat",  # becomes up/down once we have day-over-day history
            "evidence": f"{count} mention(s) across this week's signals",
        })
    return out


def _shortages() -> list[dict]:
    """Flatten the Cedefop EU skills-shortage dataset into a list."""
    try:
        data = eu_skills.get_shortage_data(limit_per_country=4)
    except Exception as exc:
        logger.warning("Could not load Cedefop shortages: %s", exc)
        return []
    out = []
    for country, shortages in data.items():
        for occupation, severity in shortages:
            out.append({"country": country, "occupation": occupation, "severity": severity})
    return out


def build_deterministic(items: list[dict], days: int) -> dict:
    """Build the full data.json payload using only rules (no LLM)."""
    classified = [i for i in items if i.get("signal_type") not in (None, "", "unknown")]

    events = _cluster_layoff_events(classified)
    vacancies = Counter(
        i.get("country") for i in classified if i.get("signal_type") == "job_posting"
    )

    # Per-country distinct-event counts (exclude pan-EU aggregates).
    by_country_events: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        c = ev.get("country")
        if c and c not in AGGREGATES:
            by_country_events[c].append(ev)

    max_events = max((len(v) for v in by_country_events.values()), default=0)
    countries = []
    for name, evs in by_country_events.items():
        n = len(evs)
        score = round(n / max_events, 2) if max_events else 0.0
        headline_ev = max(evs, key=lambda e: (e.get("jobs_affected") or 0, e.get("date") or ""))
        countries.append({
            "name": name,
            "code": config.COUNTRY_CODES.get(name, name[:2].upper()),
            "layoff_level": _layoff_level(score),
            "layoff_score": score,
            "events": n,
            "vacancies": int(vacancies.get(name, 0)),
            "headline": headline_ev.get("title"),
            "headline_url": headline_ev.get("url"),
            "summary": f"{n} layoff/restructuring event(s) tracked this period.",
        })
    countries.sort(key=lambda c: c["layoff_score"], reverse=True)

    # Top events ranked by jobs affected, then by recency.
    top_events = sorted(
        ({k: v for k, v in e.items() if not k.startswith("_")} for e in events),
        key=lambda e: (e.get("jobs_affected") or 0, e.get("date") or ""),
        reverse=True,
    )[:12]

    rising = _rising_skills(classified)
    shortages = _shortages()

    n_lay = len(events)
    n_vac = sum(vacancies.values())
    hottest = countries[0]["name"] if countries else None
    summary = (
        f"This period the radar tracked {n_lay} distinct layoff/restructuring "
        f"event(s) and {n_vac} live vacancies across Europe"
        + (f", with activity concentrated in {hottest}." if hottest else ".")
        + " EU skills shortages remain pronounced in healthcare and skilled trades (Cedefop)."
    )

    return {
        "generated_at": _utcnow_iso(),
        "period": _period_label(days),
        "summary": summary,
        "countries": countries,
        "top_events": top_events,
        "rising_skills": rising,
        "shortages": shortages,
        "sources_count": len({i.get("source_name") for i in classified if i.get("source_name")}),
    }


# ---------------------------------------------------------------------------
# Optional Claude Haiku refinement
# ---------------------------------------------------------------------------
def _haiku_refine(payload: dict, items: list[dict]) -> dict:
    """
    Ask Haiku to improve the narrative, event clustering, per-country one-liners
    and rising-skill labels. Returns a refined payload, or the original on any
    failure. Deterministic scores/vacancies/shortages are preserved.
    """
    if config.LLM_PROVIDER != "anthropic" or not config.ANTHROPIC_API_KEY:
        return payload
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed — skipping Haiku refinement.")
        return payload

    classified = [i for i in items if i.get("signal_type") in LAYOFF_SIGNALS]
    lines = []
    for i in classified[:120]:
        meta = f"[{i.get('signal_type')}|{i.get('country') or '-'}|{i.get('company') or '-'}]"
        lines.append(f"{meta} {i.get('title')}")
    item_blob = "\n".join(lines)

    prompt = (
        "You are an analyst for a daily EU job-market dashboard. Below are this "
        "period's layoff/restructuring news items (many outlets cover the same "
        "event). Return STRICT JSON only (no prose, no code fences) with keys:\n"
        '{"summary": "2-3 sentence neutral narrative of EU layoff + hiring trends",\n'
        ' "top_events": [{"company","country","type","jobs_affected"(int or null),'
        '"title","url"(copy from a matching item if known else null),"date"}],\n'
        ' "country_notes": {"<CountryName>": "one-line situation summary"}}\n'
        "Rules: CLUSTER duplicate coverage into one event each; extract the real "
        "jobs-affected number when stated; max 12 events ranked by jobs_affected; "
        "do not invent companies or numbers not present in the items.\n\n"
        f"ITEMS:\n{item_blob}\n\n"
        "Existing deterministic top_events (for url reference):\n"
        + json.dumps(payload.get("top_events", [])[:12])
    )

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.get_llm_model() or "claude-haiku-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        # Strip accidental code fences.
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        refined = json.loads(text)
    except Exception as exc:
        logger.warning("Haiku refinement failed (%s) — using deterministic data.", exc)
        return payload

    # Merge selectively; keep deterministic scores/vacancies/shortages/skills.
    if isinstance(refined.get("summary"), str) and refined["summary"].strip():
        payload["summary"] = refined["summary"].strip()
    if isinstance(refined.get("top_events"), list) and refined["top_events"]:
        # VET SOURCES: every displayed event must link to a real collected
        # article. Validate each refined event's URL against the items; if the
        # LLM didn't supply a real one, resolve it by company/title match,
        # else drop the event so nothing unverifiable reaches readers.
        url_to_item = {i["url"]: i for i in items if i.get("url")}
        vetted = []
        for ev in refined["top_events"][:14]:
            if not isinstance(ev, dict) or not ev.get("title"):
                continue
            match = url_to_item.get(ev.get("url")) or _resolve_event_item(ev, items)
            if not match:
                continue
            # Source the URL AND the date from the real article — the LLM does
            # not know real publication dates (it was hallucinating 2026-01-01).
            ev["url"] = match["url"]
            real_date = (match.get("published_at") or match.get("collected_at") or "")[:10]
            if real_date:
                ev["date"] = real_date
            vetted.append(ev)
        if vetted:
            payload["top_events"] = vetted[:12]
    notes = refined.get("country_notes") or {}
    if isinstance(notes, dict):
        for c in payload["countries"]:
            note = notes.get(c["name"])
            if isinstance(note, str) and note.strip():
                c["summary"] = note.strip()
    payload["llm"] = config.get_llm_model()
    logger.info("Haiku refinement applied.")
    return payload


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def generate_data(days: int = 7) -> dict:
    """Build the data.json payload (deterministic + optional Haiku refine)."""
    items = get_recent_items(days=days)
    logger.info("Building data.json from %d item(s) (last %d days)", len(items), days)
    payload = build_deterministic(items, days)
    payload = _haiku_refine(payload, items)
    return payload


def export(days: int = 7, path=None) -> str:
    """Generate and write data.json. Returns the path written."""
    payload = generate_data(days=days)
    out_path = path or config.DATA_JSON_PATH
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Wrote %s (%d countries, %d events, %d skills, %d shortages)",
        out_path, len(payload["countries"]), len(payload["top_events"]),
        len(payload["rising_skills"]), len(payload["shortages"]),
    )
    return str(out_path)
