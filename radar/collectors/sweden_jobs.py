"""
Sweden job-board collector.

Source: Arbetsförmedlingen (Swedish Public Employment Service) via the official
JobTech open API — a public JSON endpoint that needs no API key. This is the
polite, sanctioned alternative to scraping a job board.

API docs: https://jobtechdev.se/
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import config
from radar.models import Item
from radar.utils.http import get
from radar.utils.logging import get_logger

logger = get_logger(__name__)

SOURCE_NAME = "Arbetsförmedlingen (Sweden)"


def _ad_to_item(ad: dict) -> Item | None:
    """Convert one JobTech ad into an Item, or None if it lacks a title/url."""
    title = (ad.get("headline") or "").strip()
    url = (ad.get("webpage_url") or "").strip()
    if not title or not url:
        return None

    employer = ((ad.get("employer") or {}).get("name") or "").strip() or None
    address = ad.get("workplace_address") or {}
    municipality = (address.get("municipality") or "").strip()
    occupation = ((ad.get("occupation") or {}).get("label") or "").strip()
    field = ((ad.get("occupation_field") or {}).get("label") or "").strip() or None

    summary_bits = [b for b in (occupation, municipality) if b]
    summary = " — ".join(summary_bits) if summary_bits else None

    return Item(
        source_type="job_board",
        source_name=SOURCE_NAME,
        title=title,
        url=url,
        published_at=(ad.get("publication_date") or None),
        country="Sweden",
        company=employer,
        sector=field,
        signal_type="job_posting",
        summary=summary,
        raw_text=summary,
    )


def collect() -> list[Item]:
    items: list[Item] = []
    for term in config.JOB_SEARCH_TERMS:
        params = {
            "q": term,
            "limit": config.JOB_BOARD_LIMIT_PER_QUERY,
            "sort": "pubdate-desc",  # newest first
        }
        resp = get(f"{config.SWEDEN_JOBS_API}?{urlencode(params)}")
        if resp is None:
            continue
        try:
            hits = resp.json().get("hits") or []
        except (json.JSONDecodeError, ValueError):
            logger.warning("Sweden: non-JSON response for '%s'", term)
            continue

        logger.info("Sweden '%s': %d ad(s)", term, len(hits))
        for ad in hits:
            item = _ad_to_item(ad)
            if item:
                items.append(item)

    logger.info("Sweden collector produced %d items", len(items))
    return items
