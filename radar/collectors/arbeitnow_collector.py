"""
Arbeitnow collector.

Arbeitnow exposes a free, public, no-key job-board API focused on Europe (many
German and EU listings). This adds live vacancy signals beyond the national
public-employment-service APIs.

API: https://www.arbeitnow.com/api/job-board-api
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import config
from radar.models import Item
from radar.utils.http import get
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def _epoch_to_iso(value) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def collect() -> list[Item]:
    resp = get(config.ARBEITNOW_API)
    if resp is None:
        return []
    try:
        jobs = resp.json().get("data") or []
    except (json.JSONDecodeError, ValueError):
        logger.warning("Arbeitnow: non-JSON response")
        return []

    items: list[Item] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()
        if not title or not url:
            continue
        company = (job.get("company_name") or "").strip() or None
        location = (job.get("location") or "").strip()
        items.append(
            Item(
                source_type="job_board",
                source_name="Arbeitnow",
                title=title,
                url=url,
                published_at=_epoch_to_iso(job.get("created_at")),
                company=company,
                sector=", ".join(job.get("tags") or [])[:80] or None,
                signal_type="job_posting",
                summary=location or None,
                raw_text=location or None,
            )
        )

    logger.info("Arbeitnow collector produced %d items", len(items))
    return items
