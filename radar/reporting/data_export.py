"""
data.json generator — the public snapshot consumed by the website.

Scope: Sweden + Denmark only (config.FOCUS_COUNTRIES), over a 30-day window
("biggest moves this month").

JSON contract:
{
  generated_at, period,
  summary,                         # one short line (meta description)
  insights: ["…actionable…", …],   # 3-4 reader-facing takeaways
  countries: [{name, code, layoff_level, layoff_score, events, vacancies,
               vacancies_url, headline, headline_url, summary}],
  events: [{company, country, city, type, jobs_affected, title, title_en,
            url, date, sources:[{title, url, date, source}]}],   # deduped
  demand:  [{country, role, vacancies, share}],   # real per-country vacancy demand
  shortages: [{country, occupation, severity, source}],
  sources_count
}

Two layers: a deterministic baseline (always works, no API key) and an optional
Claude Haiku pass that (a) writes the actionable insights, (b) TRANSLATES each
event headline into plain English (title_en), and (c) writes per-country notes.
Any failure falls back to deterministic output.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote_plus

import config
from radar.db import get_recent_items
from radar.reporting import eu_skills
from radar.utils.logging import get_logger

logger = get_logger(__name__)

AGGREGATES = {"Europe", "EU"}
LAYOFF_SIGNALS = {"layoff", "restructuring", "hiring_freeze"}


def _period_label(days: int) -> str:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return f"{start.strftime('%b %d').lstrip('0')} – {end.strftime('%b %d, %Y').lstrip('0')}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- jobs-affected extraction ------------------------------------------------
_JOBS_NEAR_NOUN = re.compile(
    r"(\d{1,3}(?:[,.]\d{3})+|\d{2,6})\s*"
    r"(?:jobs|positions|roles|employees|workers|staff|posts|anställda|"
    r"medarbejdere|medarbetare|jobb|stillinger|tjänster)",
    re.I,
)
_VERB_NEAR_NUM = re.compile(
    r"(?:cut|lay[\s-]?off|laying off|axe|reduce|reducing|eliminate|slash|"
    r"shed|trim|let go|redundanc\w*|varslar|varslas|säger upp|fyrer|afskedig\w*)"
    r"\s+(?:up to\s+|around\s+|nearly\s+|about\s+|cirka\s+|omkring\s+)?"
    r"(\d{1,3}(?:[,.]\d{3})+|\d{2,6})",
    re.I,
)


def _extract_jobs_affected(*texts: str | None) -> int | None:
    best = 0
    for text in texts:
        if not text:
            continue
        for pat in (_JOBS_NEAR_NOUN, _VERB_NEAR_NUM):
            for m in pat.finditer(text):
                n = int(re.sub(r"[,.]", "", m.group(1)))
                if 10 <= n <= 500_000:
                    best = max(best, n)
    return best or None


# --- normalisation helpers ---------------------------------------------------
_STOPWORDS = set(
    "the a an of to in on for and or with at by as is are was were after over up "
    "från och i på för en ett att som de det av till med om vid efter "
    "og af til med på for en et at som de der det har ikke "
    "news jobs job cuts layoffs layoff amid".split()
)


def _title_key(title: str | None) -> str:
    """Normalised signature for clustering near-duplicate headlines."""
    t = (title or "").lower()
    t = re.sub(r"\s[\-|–—:]\s[^\-|–—:]{0,40}$", "", t)  # drop " - outlet" suffix
    words = [w for w in re.findall(r"\w+", t) if len(w) > 2 and w not in _STOPWORDS]
    return " ".join(words[:5])


_CITY_ALIASES = {
    "Stockholm": ["stockholm"],
    "Göteborg": ["göteborg", "goteborg", "gothenburg"],
    "Malmö": ["malmö", "malmo"],
    "Uppsala": ["uppsala"],
    "Västerås": ["västerås", "vasteras"],
    "Linköping": ["linköping", "linkoping"],
    "Örebro": ["örebro", "orebro"],
    "Helsingborg": ["helsingborg"],
    "København": ["københavn", "kobenhavn", "copenhagen", "kbh"],
    "Aarhus": ["aarhus", "århus"],
    "Odense": ["odense"],
    "Aalborg": ["aalborg", "ålborg"],
    "Esbjerg": ["esbjerg"],
    "Roskilde": ["roskilde"],
}


def _detect_city(*texts: str | None) -> str | None:
    haystack = " ".join(t for t in texts if t).lower()
    if not haystack.strip():
        return None
    for canonical, aliases in _CITY_ALIASES.items():
        if any(a in haystack for a in aliases):
            return canonical
    return None


def _compile_company(name: str):
    low = name.lower()
    if re.fullmatch(r"[a-z0-9 ]+", low):
        return (name, re.compile(r"\b" + re.escape(low) + r"\b"))
    return (name, low)


_COMPANY_MATCHERS = [_compile_company(n) for n in config.COMPANY_WATCHLIST]


def _detect_company(text: str | None) -> str | None:
    """Return the first watch-listed employer named in the HEADLINE, else None."""
    haystack = (text or "").lower()
    if not haystack.strip():
        return None
    for name, matcher in _COMPANY_MATCHERS:
        if isinstance(matcher, str):
            if matcher in haystack:
                return name
        elif matcher.search(haystack):
            return name
    return None


# --- event clustering --------------------------------------------------------
def _cluster_layoff_events(items: list[dict]) -> list[dict]:
    """
    Collapse layoff/restructuring articles into DISTINCT events.

    Cluster key = detected employer + country (news rarely carries a structured
    company, so we scan the headline) else a normalised title signature. Each
    cluster keeps the list of source articles for the website's deep-dive.
    """
    clusters: dict[str, dict] = {}
    for item in items:
        if item.get("signal_type") not in LAYOFF_SIGNALS:
            continue
        country = item.get("country")
        title = item.get("title") or ""
        company = (item.get("company") or "").strip() or (_detect_company(title) or "")
        key = f"{company.lower()}|{country}" if company else _title_key(title)
        jobs = _extract_jobs_affected(title, item.get("summary"))
        src = {
            "title": title,
            "url": item.get("url"),
            "date": (item.get("published_at") or item.get("collected_at") or "")[:10],
            "source": item.get("source_name"),
        }

        c = clusters.get(key)
        if c is None:
            clusters[key] = {
                "company": company or None,
                "country": country,
                "city": _detect_city(title, item.get("summary")),
                "type": item.get("signal_type"),
                "jobs_affected": jobs,
                "title": title,
                "url": item.get("url"),
                "date": src["date"],
                "sources": [src],
            }
        else:
            if jobs and (not c["jobs_affected"] or jobs > c["jobs_affected"]):
                c["jobs_affected"] = jobs
                c["title"] = title  # prefer the headline that states the number
                c["url"] = item.get("url")
            if not c.get("city"):
                c["city"] = _detect_city(title, item.get("summary"))
            if src["url"] and src["url"] not in {s["url"] for s in c["sources"]}:
                c["sources"].append(src)
    for c in clusters.values():
        c["sources"].sort(key=lambda s: s.get("date") or "", reverse=True)
        # The event's date is the most RECENT coverage (a stale republish from one
        # outlet shouldn't make a current event look years old).
        if c["sources"] and c["sources"][0].get("date"):
            c["date"] = c["sources"][0]["date"]
        c["sources"] = c["sources"][:10]
    return list(clusters.values())


def _layoff_level(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "elevated"
    if score >= 0.10:
        return "moderate"
    return "low"


# --- real per-country demand (replaces keyword "rising skills") --------------
def _demand(items: list[dict], limit: int = 6) -> list[dict]:
    """Most in-demand roles per country from actual job-board vacancy counts."""
    out: list[dict] = []
    for country in config.FOCUS_COUNTRIES:
        counter: Counter = Counter()
        for i in items:
            if i.get("country") == country and i.get("signal_type") == "job_posting":
                sector = (i.get("sector") or "").strip()
                if sector:
                    counter[sector] += 1
        if not counter:
            continue
        total = sum(counter.values())
        for role, n in counter.most_common(limit):
            out.append({
                "country": country,
                "role": role.title() if role.islower() else role,
                "vacancies": n,
                "share": round(n / total * 100),
            })
    return out


def _shortages() -> list[dict]:
    """Cedefop skills-shortage occupations for Sweden, Denmark (+ EU27)."""
    try:
        data = eu_skills.get_shortage_data(
            limit_per_country=config.CEDEFOP_LIMIT_PER_COUNTRY
        )
    except Exception as exc:
        logger.warning("Could not load Cedefop shortages: %s", exc)
        return []
    out = []
    for country, shortages in data.items():
        for occupation, severity in shortages:
            out.append({
                "country": country,
                "occupation": occupation,
                "severity": severity,
                "source": "Cedefop CLSSI 2024",
            })
    return out


def _vacancy_url(country: str, role: str | None) -> str | None:
    tmpl = config.VACANCY_BOARD_URLS.get(country)
    if not tmpl:
        return None
    return tmpl.format(q=quote_plus(role or ""))


# --- deterministic baseline --------------------------------------------------
def build_deterministic(items: list[dict], days: int) -> dict:
    classified = [i for i in items if i.get("signal_type") not in (None, "", "unknown")]

    # Substantive events only: a named employer OR a stated jobs-affected number.
    # This is the fix for un-attributable one-off headlines inflating the count.
    # Also enforce recency by the event's newest coverage date, so "this month"
    # really means this month (some feeds resurface years-old articles).
    cutoff = (date.today() - timedelta(days=days + 3)).isoformat()
    events = [
        e for e in _cluster_layoff_events(classified)
        if (e.get("company") or e.get("jobs_affected"))
        and (not e.get("date") or e["date"] >= cutoff)
    ]
    vacancies = Counter(
        i.get("country") for i in classified if i.get("signal_type") == "job_posting"
    )

    by_country: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        if ev.get("country") in config.FOCUS_COUNTRIES:
            by_country[ev["country"]].append(ev)

    demand = _demand(classified)
    top_role: dict[str, str] = {}
    for d in demand:  # demand is ranked, so the first per country is the top one
        if d.get("role"):
            top_role.setdefault(d["country"], d["role"])

    max_events = max((len(by_country[c]) for c in config.FOCUS_COUNTRIES), default=0)
    countries = []
    for name in config.FOCUS_COUNTRIES:
        evs = by_country.get(name, [])
        n = len(evs)
        score = round(n / max_events, 2) if max_events else 0.0
        headline_ev = (
            max(evs, key=lambda e: (e.get("jobs_affected") or 0, e.get("date") or ""))
            if evs else None
        )
        countries.append({
            "name": name,
            "code": config.COUNTRY_CODES.get(name, name[:2].upper()),
            "layoff_level": _layoff_level(score),
            "layoff_score": score,
            "events": n,
            "vacancies": int(vacancies.get(name, 0)),
            "vacancies_url": _vacancy_url(name, top_role.get(name)),
            "headline": headline_ev.get("title") if headline_ev else None,
            "headline_url": headline_ev.get("url") if headline_ev else None,
            "summary": f"{n} workforce event(s) and {int(vacancies.get(name, 0))} sampled vacancies.",
        })
    countries.sort(key=lambda c: c["layoff_score"], reverse=True)

    # All substantive events, ranked by jobs affected then recency.
    all_events = sorted(
        (e for e in events if e.get("country") in config.FOCUS_COUNTRIES),
        key=lambda e: (e.get("jobs_affected") or 0, e.get("date") or ""),
        reverse=True,
    )
    for e in all_events:
        e["title_en"] = e["title"]  # Haiku overwrites with a plain-English version

    shortages = _shortages()
    insights = _deterministic_insights(countries, all_events, demand, shortages)

    return {
        "generated_at": _utcnow_iso(),
        "period": _period_label(days),
        "summary": insights[0] if insights else "Sweden & Denmark job-market snapshot.",
        "insights": insights,
        "countries": countries,
        "events": all_events,
        "demand": demand,
        "shortages": shortages,
        "sources_count": len({i.get("source_name") for i in classified if i.get("source_name")}),
    }


def _deterministic_insights(countries, events, demand, shortages) -> list[str]:
    out: list[str] = []
    if countries:
        hot = countries[0]
        other = countries[1] if len(countries) > 1 else None
        if hot["events"] or (other and other["events"]):
            line = f"{hot['name']} shows more layoff pressure ({hot['events']} events"
            if other:
                line += f" vs {other['events']} in {other['name']}"
            out.append(line + ").")
    biggest = next((e for e in events if e.get("jobs_affected")), None)
    if biggest:
        who = biggest.get("company") or "An employer"
        out.append(
            f"Largest single cut: {who} — {biggest['jobs_affected']:,} roles "
            f"({biggest['country']})."
        )
    if demand:
        bits = []
        for country in config.FOCUS_COUNTRIES:
            top = next((d for d in demand if d["country"] == country), None)
            if top:
                bits.append(f"{top['role']} in {country}")
        if bits:
            out.append("Most-advertised roles: " + "; ".join(bits) + ".")
    if shortages:
        worst = max(shortages, key=lambda s: s["severity"])
        out.append(
            f"Sharpest skills shortage: {worst['occupation']} "
            f"({worst['country']}, severity {worst['severity']}/4)."
        )
    return out[:4]


# --- Claude Haiku refinement: insights + English translation -----------------
def _haiku_refine(payload: dict, items: list[dict]) -> dict:
    if config.LLM_PROVIDER != "anthropic" or not config.ANTHROPIC_API_KEY:
        return payload
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed — skipping Haiku refinement.")
        return payload

    events = payload.get("events", [])[:40]
    ev_lines = [
        {"i": idx, "country": e.get("country"), "company": e.get("company"),
         "jobs": e.get("jobs_affected"), "title": e.get("title")}
        for idx, e in enumerate(events)
    ]
    prompt = (
        "You are an analyst for a Sweden & Denmark job-market dashboard. The "
        "events below are real, already-deduplicated layoff/restructuring events "
        "(headlines may be Swedish or Danish). Return STRICT JSON only (no prose, "
        "no code fences):\n"
        '{"insights": ["3 to 4 short, specific, actionable takeaways for a reader '
        '(HR or jobseeker), plain English, each <= 22 words"],\n'
        ' "country_notes": {"Sweden": "one-line situation", "Denmark": "one-line situation"},\n'
        ' "titles_en": {"<i>": "the event title translated into concise plain English"}}\n'
        "Rules: translate EVERY event title to English in titles_en keyed by its "
        "index i; keep company names and numbers; do not invent events.\n\n"
        f"EVENTS:\n{json.dumps(ev_lines, ensure_ascii=False)}\n"
    )
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.get_llm_model() or "claude-haiku-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        refined = json.loads(text)
    except Exception as exc:
        logger.warning("Haiku refinement failed (%s) — using deterministic data.", exc)
        return payload

    if isinstance(refined.get("insights"), list) and refined["insights"]:
        payload["insights"] = [str(s).strip() for s in refined["insights"] if str(s).strip()][:4]
        if payload["insights"]:
            payload["summary"] = payload["insights"][0]
    titles = refined.get("titles_en") or {}
    if isinstance(titles, dict):
        for idx, e in enumerate(events):
            t = titles.get(str(idx)) or titles.get(idx)
            if isinstance(t, str) and t.strip():
                e["title_en"] = t.strip()
    notes = refined.get("country_notes") or {}
    if isinstance(notes, dict):
        for c in payload["countries"]:
            note = notes.get(c["name"])
            if isinstance(note, str) and note.strip():
                c["summary"] = note.strip()
    payload["llm"] = config.get_llm_model()
    logger.info("Haiku refinement applied (insights + %d translations).", len(titles))
    return payload


# --- public entry points -----------------------------------------------------
def generate_data(days: int = 30) -> dict:
    items = get_recent_items(days=days)
    logger.info("Building data.json from %d item(s) (last %d days)", len(items), days)
    payload = build_deterministic(items, days)
    payload = _haiku_refine(payload, items)
    return payload


def export(days: int = 30, path=None) -> str:
    payload = generate_data(days=days)
    out_path = path or config.DATA_JSON_PATH
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Wrote %s (%d countries, %d events, %d demand, %d shortages)",
        out_path, len(payload["countries"]), len(payload["events"]),
        len(payload["demand"]), len(payload["shortages"]),
    )
    return str(out_path)
