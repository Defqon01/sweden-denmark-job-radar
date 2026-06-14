"""
Germany job-board collector.

Source: Bundesagentur für Arbeit (German Federal Employment Agency) "Jobsuche"
API. It is a public JSON API; reading public vacancies only needs the
well-known public app key (no personal registration), which we send in the
"X-API-Key" header.

Job titles come back in German — we do not translate them.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import config
from radar.models import Item
from radar.utils.http import get
from radar.utils.logging import get_logger

logger = get_logger(__name__)

SOURCE_NAME = "Bundesagentur für Arbeit (Germany)"


def _ad_to_item(ad: dict) -> Item | None:
    """Convert one Bundesagentur ad into an Item, or None if unusable."""
    title = (ad.get("titel") or ad.get("beruf") or "").strip()
    refnr = (ad.get("refnr") or "").strip()
    if not title or not refnr:
        return None

    url = config.GERMANY_JOB_DETAIL_URL.format(refnr=refnr)
    employer = (ad.get("arbeitgeber") or "").strip() or None
    location = (ad.get("arbeitsort") or {}).get("ort", "")
    location = (location or "").strip()
    summary = location or None

    return Item(
        source_type="job_board",
        source_name=SOURCE_NAME,
        title=title,
        url=url,
        published_at=(ad.get("aktuelleVeroeffentlichungsdatum") or None),
        country="Germany",
        company=employer,
        signal_type="job_posting",
        summary=summary,
        raw_text=summary,
    )


def collect() -> list[Item]:
    items: list[Item] = []
    headers = {"X-API-Key": config.GERMANY_JOBS_API_KEY}
    for term in config.JOB_SEARCH_TERMS:
        # "was" means "what" (the search keyword); "size" caps the results.
        params = {"was": term, "size": config.JOB_BOARD_LIMIT_PER_QUERY}
        resp = get(
            f"{config.GERMANY_JOBS_API}?{urlencode(params)}",
            extra_headers=headers,
        )
        if resp is None:
            continue
        try:
            ads = resp.json().get("stellenangebote") or []
        except (json.JSONDecodeError, ValueError):
            logger.warning("Germany: non-JSON response for '%s'", term)
            continue

        logger.info("Germany '%s': %d ad(s)", term, len(ads))
        for ad in ads:
            item = _ad_to_item(ad)
            if item:
                items.append(item)

    logger.info("Germany collector produced %d items", len(items))
    return items
