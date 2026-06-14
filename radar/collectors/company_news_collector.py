"""
Company news collector.

For each company in config.COMPANY_FEEDS that has a known RSS URL, we parse the
feed and turn entries into Items tagged with the company name. Companies whose
feed URL is None are skipped safely (with a TODO logged) so the run never
crashes just because we don't yet have a feed for them.
"""

from __future__ import annotations

import feedparser

import config
from radar.models import Item
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def _published_iso(entry) -> str | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed:
        from datetime import datetime, timezone

        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None


def collect() -> list[Item]:
    items: list[Item] = []
    for company, url in config.COMPANY_FEEDS:
        if not url:
            # No public feed configured yet — skip without crashing.
            logger.info("No RSS feed for %s yet (TODO) — skipping", company)
            continue

        try:
            parsed = feedparser.parse(url, agent=config.USER_AGENT)
            entries = parsed.entries or []
        except Exception as exc:
            logger.warning("Failed to parse %s feed (%s): %s", company, url, exc)
            continue

        logger.info("Company '%s': %d entries", company, len(entries))
        for entry in entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue
            summary = getattr(entry, "summary", None)
            items.append(
                Item(
                    source_type="company_news",
                    source_name=company,
                    company=company,
                    title=title,
                    url=link,
                    published_at=_published_iso(entry),
                    summary=summary,
                    raw_text=summary,
                )
            )

    logger.info("Company news collector produced %d items", len(items))
    return items
