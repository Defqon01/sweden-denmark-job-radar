"""
Report generator.

Produces a concise weekly markdown report from the items collected in the last
N days. Two paths:

1. LLM path (if LLM_PROVIDER is openai/anthropic and a key is present):
   we hand a compact summary of the items to the model and ask it to write the
   report in our required structure.

2. Deterministic fallback (default): we build the report purely from counts,
   keywords, and the newest items — no API key required. This always works.

Both paths return a markdown string. The caller is responsible for saving it.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

import config
from radar.processing.keyword_extractor import top_keywords
from radar.reporting import eu_skills
from radar.utils.logging import get_logger

logger = get_logger(__name__)

# The section headers we always want, in order.
REPORT_SECTIONS = [
    "Executive summary",
    "Country layoff thermometer",
    "Layoff and restructuring signals",
    "Hiring and job-market signals",
    "Skills shortages across the EU",
    "Emerging roles and keywords",
    "What this means for HR / Talent / Workforce Planning",
    "Sources reviewed",
]

# "Europe" / "EU" are broad aggregates, not single countries — handled apart
# from the per-country thermometer.
_COUNTRY_AGGREGATES = {"Europe", "EU"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _today_str() -> str:
    return date.today().isoformat()


def _count_by(items: list[dict], key: str) -> Counter:
    counter: Counter = Counter()
    for item in items:
        value = item.get(key) or "unknown"
        counter[value] += 1
    return counter


def _items_with_signal(items: list[dict], signal_types: set[str]) -> list[dict]:
    return [i for i in items if i.get("signal_type") in signal_types]


def _format_item_line(item: dict) -> str:
    title = item.get("title") or "(untitled)"
    url = item.get("url") or ""
    bits = []
    if item.get("country"):
        bits.append(item["country"])
    if item.get("company"):
        bits.append(item["company"])
    suffix = f" _({', '.join(bits)})_" if bits else ""
    if url:
        return f"- [{title}]({url}){suffix}"
    return f"- {title}{suffix}"


def _title_key(title: str | None) -> str:
    """A loose key for spotting near-duplicate headlines (same story, many outlets)."""
    words = re.findall(r"\w+", (title or "").lower())
    return " ".join(words[:6])


def _curate(items: list[dict], limit: int) -> list[dict]:
    """
    Pick the most useful items: prefer those naming both a company and a
    country, drop near-duplicate headlines, and cap the count.
    """
    concrete = [i for i in items if i.get("company") and i.get("country")]
    rest = [i for i in items if not (i.get("company") and i.get("country"))]
    seen: set[str] = set()
    out: list[dict] = []
    for item in concrete + rest:
        key = _title_key(item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _thermometer_rows(layoff_items: list[dict]) -> tuple[list[str], int]:
    """
    Build a per-country layoff-intensity gauge.

    Returns (markdown rows, pan-European aggregate count). Each row is a bar
    scaled to the busiest country, with a Low/Moderate/Elevated/High label.
    """
    counts: Counter = Counter()
    aggregate = 0
    for item in layoff_items:
        country = item.get("country")
        if not country:
            continue
        if country in _COUNTRY_AGGREGATES:
            aggregate += 1
        else:
            counts[country] += 1

    if not counts:
        return [], aggregate

    top = counts.most_common(12)
    max_count = top[0][1]
    rows = []
    for country, n in top:
        ratio = n / max_count if max_count else 0
        filled = max(1, round(ratio * 10))
        bar = "█" * filled + "░" * (10 - filled)
        if ratio >= 0.66:
            label = "High"
        elif ratio >= 0.33:
            label = "Elevated"
        elif ratio >= 0.10:
            label = "Moderate"
        else:
            label = "Low"
        rows.append(f"- **{country}** {bar} {label} ({n})")
    return rows, aggregate


# ---------------------------------------------------------------------------
# Deterministic fallback report
# ---------------------------------------------------------------------------
def generate_fallback_report(
    items: list[dict],
    days: int,
    skills_data: dict[str, list[tuple[str, float]]] | None = None,
) -> str:
    """Build a curated markdown report from counts, simple rules, and the
    Cedefop EU skills-shortage dataset."""
    today = _today_str()
    skills_data = skills_data or {}

    # Keep only classified items in the report (unclassified stay in the DB).
    all_count = len(items)
    items = [i for i in items if i.get("signal_type") not in (None, "", "unknown")]
    omitted = all_count - len(items)
    total = len(items)

    layoff_resto = _items_with_signal(items, {"layoff", "restructuring", "hiring_freeze"})
    hiring = _items_with_signal(items, {"job_posting"})
    skills_news = _items_with_signal(items, {"skills_shortage"})
    labour_news = _items_with_signal(items, {"labour_market_news"})
    keywords = top_keywords(items, limit=8)

    thermo_rows, eu_aggregate = _thermometer_rows(layoff_resto)

    lines: list[str] = []
    lines.append(f"# EU Job Market Radar — {today}")
    lines.append("")
    omitted_note = f" ({omitted} unclassified headlines filtered out)" if omitted else ""
    lines.append(
        f"_Last {days} days · {total} classified signals{omitted_note} · "
        f"deterministic mode (no LLM)._"
    )
    lines.append("")

    # 1. Executive summary — one tight narrative paragraph.
    lines.append("## Executive summary")
    if total == 0:
        lines.append("No classified signals this week.")
    else:
        hottest = thermo_rows[0] if thermo_rows else ""
        hottest_country = (
            hottest.split("**")[1] if "**" in hottest else None
        )
        hot_sentence = (
            f" Layoff/restructuring chatter was loudest around **{hottest_country}**."
            if hottest_country
            else ""
        )
        skills_sentence = (
            " EU skills-shortage data (Cedefop) is included below."
            if skills_data
            else ""
        )
        lines.append(
            f"The radar tracked **{len(layoff_resto)}** layoff/restructuring signals, "
            f"**{len(hiring)}** live job-board vacancies, "
            f"**{len(skills_news)}** skills-shortage news items and "
            f"**{len(labour_news)}** broader labour-market stories this week."
            f"{hot_sentence}{skills_sentence}"
        )
    lines.append("")

    # 2. Country layoff thermometer.
    lines.append("## Country layoff thermometer")
    if thermo_rows:
        lines.append(
            "_Relative intensity of layoff / restructuring / hiring-freeze "
            "signals per country (bar scaled to the busiest country)._"
        )
        lines.append("")
        lines.extend(thermo_rows)
        if eu_aggregate:
            lines.append(
                f"- _Plus {eu_aggregate} signal(s) tagged Europe/EU-wide rather "
                f"than a single country._"
            )
    else:
        lines.append("_No country-specific layoff signals this week._")
    lines.append("")

    # 3. Layoff and restructuring signals — curated, de-duplicated.
    lines.append("## Layoff and restructuring signals")
    curated_layoffs = _curate(layoff_resto, 8)
    if curated_layoffs:
        lines.append(
            f"_{len(layoff_resto)} signals collected; showing the {len(curated_layoffs)} "
            f"most concrete (company + country named)._"
        )
        lines.append("")
        for item in curated_layoffs:
            lines.append(_format_item_line(item))
    else:
        lines.append("_No layoff or restructuring signals detected this week._")
    lines.append("")

    # 4. Hiring and job-market signals — vacancy summary + samples + news.
    lines.append("## Hiring and job-market signals")
    if hiring:
        by_country = Counter(i.get("country") or "Unknown" for i in hiring)
        spread = ", ".join(f"{c} ({n})" for c, n in by_country.most_common(8))
        lines.append(f"**{len(hiring)} live vacancies** from public job boards — {spread}.")
        lines.append("")
        lines.append("Sample roles:")
        for item in _curate(hiring, 8):
            lines.append(_format_item_line(item))
    else:
        lines.append(
            "_No live vacancies this week (job-board collectors disabled or empty)._"
        )
    if labour_news:
        lines.append("")
        lines.append("Broader labour-market news:")
        for item in _curate(labour_news, 5):
            lines.append(_format_item_line(item))
    lines.append("")

    # 5. Skills shortages across the EU — the Cedefop dataset is the substance.
    lines.append("## Skills shortages across the EU")
    if skills_data:
        lines.append(
            "_Top shortage occupations by country, from the **Cedefop Labour & "
            "Skills Shortage Index** (scale 1–4; 4 = severe shortage)._"
        )
        lines.append("")
        for country, shortages in skills_data.items():
            occ_str = "; ".join(f"{occ} ({idx})" for occ, idx in shortages)
            lines.append(f"- **{country}** — {occ_str}")
    else:
        lines.append(
            "_Cedefop skills-shortage dataset was unavailable this run; relying on "
            "news signals only._"
        )
    if skills_news:
        lines.append("")
        lines.append("Recent skills-shortage news:")
        for item in _curate(skills_news, 6):
            lines.append(_format_item_line(item))
    lines.append("")

    # 6. Emerging roles and keywords — brief, with context.
    lines.append("## Emerging roles and keywords")
    if keywords:
        kw_str = ", ".join(f"{kw} ({count})" for kw, count in keywords)
        lines.append(f"Most-mentioned themes across this week's signals: {kw_str}.")
    else:
        lines.append("_No notable themes detected this week._")
    lines.append("")

    # 7. What this means for HR / Talent / Workforce Planning.
    lines.append("## What this means for HR / Talent / Workforce Planning")
    for bullet in _hr_observations(
        layoff_resto, hiring, skills_news, skills_data, thermo_rows
    ):
        lines.append(f"- {bullet}")
    lines.append("")

    # 8. Sources reviewed.
    lines.append("## Sources reviewed")
    by_source = _count_by(items, "source_name")
    if by_source:
        for source, count in by_source.most_common():
            lines.append(f"- {source}: {count} item(s)")
    else:
        lines.append("_No sources produced items this week._")
    lines.append("")

    return "\n".join(lines)


def _hr_observations(
    layoff_resto: list[dict],
    hiring: list[dict],
    skills_news: list[dict],
    skills_data: dict[str, list[tuple[str, float]]],
    thermo_rows: list[str],
) -> list[str]:
    """Generate practical, context-aware HR/workforce-planning takeaways."""
    bullets = []
    if thermo_rows:
        hottest = thermo_rows[0].split("**")[1] if "**" in thermo_rows[0] else None
        if hottest:
            bullets.append(
                f"**{hottest}** shows the most layoff/restructuring activity — watch "
                f"for talent becoming available there and review internal-mobility risk."
            )
    if skills_data:
        # Pull a couple of concrete EU-wide shortage occupations for specificity.
        eu = skills_data.get("EU27") or next(iter(skills_data.values()), [])
        if eu:
            occ_names = ", ".join(occ for occ, _ in eu[:3])
            bullets.append(
                f"Persistent EU shortage occupations (e.g. {occ_names}) are where "
                f"reskilling budgets and pipelines will have the most leverage."
            )
    if hiring:
        bullets.append(
            f"{len(hiring)} live vacancies signal where competition for talent is "
            f"rising — useful for compensation benchmarking and sourcing focus."
        )
    if not bullets:
        bullets.append(
            "A quiet week: a good moment to refresh workforce-planning assumptions "
            "rather than react to news."
        )
    return bullets


# ---------------------------------------------------------------------------
# LLM-based report
# ---------------------------------------------------------------------------
def _build_llm_prompt(
    items: list[dict],
    days: int,
    skills_data: dict[str, list[tuple[str, float]]] | None = None,
) -> str:
    """Compose a compact prompt with the collected items for the LLM."""
    today = _today_str()
    skills_data = skills_data or {}
    # Send only classified items to the LLM — unclassified headlines are noise.
    items = [i for i in items if i.get("signal_type") not in (None, "", "unknown")]
    lines = [
        f"You are an analyst writing the 'EU Job Market Radar' weekly report for {today}.",
        f"Below are {len(items)} items collected over the last {days} days.",
        "",
        "Write a concise but insightful markdown report titled exactly:",
        f"# EU Job Market Radar — {today}",
        "",
        "Use these sections as level-2 headings, in this order:",
    ]
    for section in REPORT_SECTIONS:
        lines.append(f"- {section}")
    lines += [
        "",
        "Be concrete, cite item titles where useful, avoid hype, and keep it tight.",
        "Do not invent facts beyond the items provided.",
        "",
        "ITEMS (one per line: [signal_type | country | company] title — url):",
    ]
    for item in items[:120]:  # keep the prompt bounded
        meta = " | ".join(
            x for x in (
                item.get("signal_type") or "unknown",
                item.get("country") or "-",
                item.get("company") or "-",
            )
        )
        lines.append(f"[{meta}] {item.get('title')} — {item.get('url')}")

    if skills_data:
        lines += [
            "",
            "EU SKILLS-SHORTAGE DATA (Cedefop Labour & Skills Shortage Index, "
            "scale 1-4, 4=severe) — use this for the skills section:",
        ]
        for country, shortages in skills_data.items():
            occ_str = "; ".join(f"{occ} ({idx})" for occ, idx in shortages)
            lines.append(f"{country}: {occ_str}")
    return "\n".join(lines)


def _generate_with_openai(prompt: str) -> str | None:
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — falling back.")
        return None
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=config.get_llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.warning("OpenAI request failed: %s — falling back.", exc)
        return None


def _generate_with_anthropic(prompt: str) -> str | None:
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — falling back.")
        return None
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.get_llm_model(),
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate any text blocks in the response.
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
    except Exception as exc:
        logger.warning("Anthropic request failed: %s — falling back.", exc)
        return None


def generate_llm_report(
    items: list[dict],
    days: int,
    skills_data: dict[str, list[tuple[str, float]]] | None = None,
) -> str | None:
    """Try to generate the report via the configured LLM. None on failure."""
    provider = config.LLM_PROVIDER
    prompt = _build_llm_prompt(items, days, skills_data)

    if provider == "openai" and config.OPENAI_API_KEY:
        logger.info("Generating report via OpenAI (%s)", config.get_llm_model())
        return _generate_with_openai(prompt)
    if provider == "anthropic" and config.ANTHROPIC_API_KEY:
        logger.info("Generating report via Anthropic (%s)", config.get_llm_model())
        return _generate_with_anthropic(prompt)

    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def generate_report(items: list[dict], days: int = 7) -> str:
    """
    Generate the weekly report markdown.

    Tries the LLM if configured; otherwise (or on any failure) uses the
    deterministic fallback so we always return something useful.
    """
    # Fetch the EU skills-shortage data once (best-effort; {} if unavailable).
    try:
        skills_data = eu_skills.get_shortage_data(limit_per_country=5)
    except Exception as exc:  # never let the skills source break the report
        logger.warning("Could not load EU skills data: %s", exc)
        skills_data = {}

    if config.LLM_PROVIDER in ("openai", "anthropic"):
        report = generate_llm_report(items, days, skills_data)
        if report:
            return report
        logger.info("LLM unavailable/failed — using deterministic fallback report.")

    return generate_fallback_report(items, days, skills_data)
