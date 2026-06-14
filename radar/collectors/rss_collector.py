"""
RSS collector.

Two responsibilities:
1. Build Google News RSS feeds from the search queries in config and parse them.
2. Parse any direct (non-Google) RSS feeds listed in config.

feedparser handles all the messy RSS/Atom parsing for us. Network calls go
through our polite http helper where possible; feedparser itself is given a
User-Agent so feeds that block default agents still work.
"""

from __future__ import annotations

from urllib.parse import quote_plus

import feedparser

import config
from radar.models import Item
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def _published_iso(entry) -> str | None:
    """Return an ISO date string from a feed entry, if available."""
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed:
        # parsed is a time.struct_time in UTC.
        from datetime import datetime, timezone

        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None


def _parse_feed(url: str) -> list:
    """Parse a feed URL with feedparser, returning entries (never raises)."""
    try:
        # feedparser accepts request headers via the agent / request_headers args.
        parsed = feedparser.parse(url, agent=config.USER_AGENT)
        if parsed.bozo and not parsed.entries:
            logger.warning("Feed parse issue for %s: %s", url, parsed.bozo_exception)
        return parsed.entries or []
    except Exception as exc:  # feedparser is robust, but be defensive.
        logger.warning("Failed to parse feed %s: %s", url, exc)
        return []


def collect_google_news() -> list[Item]:
    """Collect items from all configured Google News RSS search queries."""
    items: list[Item] = []
    for query in config.GOOGLE_NEWS_QUERIES:
        url = config.GOOGLE_NEWS_RSS_TEMPLATE.format(query=quote_plus(query))
        entries = _parse_feed(url)
        logger.info("Google News '%s': %d entries", query, len(entries))
        for entry in entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue
            summary = getattr(entry, "summary", None)
            items.append(
                Item(
                    source_type="rss",
                    source_name=f"Google News: {query}",
                    title=title,
                    url=link,
                    published_at=_published_iso(entry),
                    summary=summary,
                    raw_text=summary,
                )
            )
    return items


def collect_direct_feeds() -> list[Item]:
    """Collect items from any direct RSS feeds configured in config."""
    items: list[Item] = []
    for source_name, url in config.DIRECT_RSS_FEEDS:
        entries = _parse_feed(url)
        logger.info("Direct feed '%s': %d entries", source_name, len(entries))
        for entry in entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue
            summary = getattr(entry, "summary", None)
            items.append(
                Item(
                    source_type="rss",
                    source_name=source_name,
                    title=title,
                    url=link,
                    published_at=_published_iso(entry),
                    summary=summary,
                    raw_text=summary,
                )
            )
    return items


def collect() -> list[Item]:
    """Collect from both Google News and direct RSS feeds."""
    items = collect_google_news() + collect_direct_feeds()
    logger.info("RSS collector produced %d items", len(items))
    return items
