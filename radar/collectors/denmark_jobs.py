"""
Denmark job-board collector.

Source: Jobindex — Denmark's largest job market — via its public search RSS
feeds (one feed per keyword, no API key, intended for syndication). The polite,
sanctioned alternative to scraping the site.

Jobindex feeds are ISO-8859-1 encoded (feedparser handles that). Each entry
title follows the pattern:

    "<role> hos <Company> i <City>, <Company A/S>"

so we recover the employer from the trailing ", …" segment and the city from
the " i <City>" segment, best-effort. The search term that produced the ad is
stored in `sector` so it can double as a demand signal per category.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

import feedparser

import config
from radar.models import Item
from radar.utils.logging import get_logger

logger = get_logger(__name__)

SOURCE_NAME = "Jobindex (Denmark)"

_CITY_RE = re.compile(r"\bi\s+([A-ZÆØÅ][\wÆØÅæøå.\- ]{1,30}?)(?:,|$)")


def _published_iso(entry) -> str | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed:
        from datetime import datetime, timezone

        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None


def _parse_title(raw_title: str) -> tuple[str, str | None, str | None]:
    """Return (role_title, company, city) from a Jobindex headline (best-effort)."""
    title = raw_title.strip()
    company = None
    if "," in title:
        head, _, tail = title.rpartition(",")
        tail = tail.strip()
        if tail and len(tail) <= 60:
            company = tail
            title = head.strip()
    city = None
    m = _CITY_RE.search(title)
    if m:
        city = m.group(1).strip()
    return title, company, city


def collect() -> list[Item]:
    items: list[Item] = []
    for term in config.JOB_SEARCH_TERMS:
        url = config.DENMARK_JOBS_RSS.format(query=quote_plus(term))
        try:
            parsed = feedparser.parse(url, agent=config.USER_AGENT)
        except Exception as exc:  # feedparser is robust, but be defensive.
            logger.warning("Denmark: failed to parse feed for '%s': %s", term, exc)
            continue
        entries = parsed.entries or []
        logger.info("Denmark '%s': %d ad(s)", term, len(entries))
        for entry in entries[: config.JOB_BOARD_LIMIT_PER_QUERY]:
            raw_title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not raw_title or not link:
                continue
            title, company, city = _parse_title(raw_title)
            items.append(
                Item(
                    source_type="job_board",
                    source_name=SOURCE_NAME,
                    title=title,
                    url=link,
                    published_at=_published_iso(entry),
                    country="Denmark",
                    company=company,
                    sector=term,  # the search term doubles as a demand category
                    signal_type="job_posting",
                    summary=city,
                    raw_text=city,
                )
            )

    logger.info("Denmark collector produced %d items", len(items))
    return items
