"""
GDELT collector.

GDELT (the Global Database of Events, Language, and Tone) is a free, open,
no-key news-event database covering thousands of outlets worldwide. Its DOC 2.0
API is TRANSLINGUAL: an English query like "layoffs" also matches local-language
coverage (German, French, Italian …), so this dramatically broadens European
layoff/restructuring coverage beyond English Google News.

We run one query per European country (by FIPS source-country code) and tag the
results as layoff signals. Titles may be in the local language — the LLM report
step understands them and produces English summaries.

GDELT is explicitly intended for programmatic use; we stay polite via the shared
rate-limited HTTP helper.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import config
from radar.models import Item
from radar.utils.http import get
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def _parse_seendate(seendate: str | None) -> str | None:
    """GDELT seendate is like '20260712T103000Z' -> ISO 8601."""
    if not seendate:
        return None
    try:
        dt = datetime.strptime(seendate[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def collect() -> list[Item]:
    items: list[Item] = []
    for fips, country in config.GDELT_COUNTRIES.items():
        params = {
            "query": f"{config.GDELT_QUERY} sourcecountry:{fips}",
            "mode": "artlist",
            "maxrecords": config.GDELT_LIMIT_PER_COUNTRY,
            "timespan": config.GDELT_TIMESPAN,
            "format": "json",
            "sort": "datedesc",
        }
        resp = get(f"{config.GDELT_API}?{urlencode(params)}")
        if resp is None:
            continue
        try:
            articles = resp.json().get("articles") or []
        except (json.JSONDecodeError, ValueError):
            # GDELT occasionally returns a non-JSON throttle notice — skip safely.
            logger.info("GDELT: non-JSON for %s (throttled?) — skipping", country)
            continue

        logger.info("GDELT %s: %d article(s)", country, len(articles))
        for art in articles:
            title = (art.get("title") or "").strip()
            url = (art.get("url") or "").strip()
            if not title or not url:
                continue
            items.append(
                Item(
                    source_type="news",
                    source_name=f"GDELT: {country}",
                    title=title,
                    url=url,
                    published_at=_parse_seendate(art.get("seendate")),
                    country=country,            # source country (good EU proxy)
                    signal_type="layoff",       # query is layoff-scoped
                    summary=title,
                    raw_text=title,
                )
            )

    logger.info("GDELT collector produced %d items", len(items))
    return items
