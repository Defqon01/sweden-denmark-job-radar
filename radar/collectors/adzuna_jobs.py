"""
Adzuna job-board collector (multi-country).

Source: Adzuna, a job-search aggregator with a free, official API that legally
aggregates listings across many EU countries. One collector covers several
countries (see config.ADZUNA_COUNTRIES).

This is the polite, sanctioned way to get broad coverage — unlike Indeed, which
forbids scraping and has no public search API.

To enable it:
1. Create free credentials at https://developer.adzuna.com/
2. Put them in your .env / GitHub secrets:
     ADZUNA_APP_ID=...
     ADZUNA_APP_KEY=...

If the credentials are missing, this collector skips safely and returns
nothing — it never crashes the run.

Job titles come back in the local language — we do not translate them.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import config
from radar.models import Item
from radar.utils.http import get
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def _result_to_item(result: dict, country_name: str) -> Item | None:
    """Convert one Adzuna result into an Item, or None if unusable."""
    title = (result.get("title") or "").strip()
    url = (result.get("redirect_url") or "").strip()
    if not title or not url:
        return None

    employer = ((result.get("company") or {}).get("display_name") or "").strip() or None
    location = ((result.get("location") or {}).get("display_name") or "").strip()
    category = ((result.get("category") or {}).get("label") or "").strip() or None

    summary_bits = [b for b in (category, location) if b]
    summary = " — ".join(summary_bits) if summary_bits else None

    return Item(
        source_type="job_board",
        source_name=f"Adzuna ({country_name})",
        title=title,
        url=url,
        published_at=(result.get("created") or None),
        country=country_name,
        company=employer,
        sector=category,
        signal_type="job_posting",
        summary=summary,
        raw_text=summary,
    )


def collect() -> list[Item]:
    if not (config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY):
        logger.info(
            "Adzuna: no credentials set — skipping safely. "
            "See adzuna_jobs.py to enable."
        )
        return []

    items: list[Item] = []
    for code, country_name in config.ADZUNA_COUNTRIES.items():
        for term in config.JOB_SEARCH_TERMS:
            params = {
                "app_id": config.ADZUNA_APP_ID,
                "app_key": config.ADZUNA_APP_KEY,
                "results_per_page": config.JOB_BOARD_LIMIT_PER_QUERY,
                "what": term,
                "content-type": "application/json",
            }
            url = f"{config.ADZUNA_API.format(country=code)}?{urlencode(params)}"
            resp = get(url)
            if resp is None:
                continue
            try:
                results = resp.json().get("results") or []
            except (json.JSONDecodeError, ValueError):
                logger.warning("Adzuna: non-JSON response for %s '%s'", code, term)
                continue

            for result in results:
                item = _result_to_item(result, country_name)
                if item:
                    items.append(item)
        logger.info("Adzuna %s (%s): collected so far %d", code, country_name, len(items))

    logger.info("Adzuna collector produced %d items", len(items))
    return items
