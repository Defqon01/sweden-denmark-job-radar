"""
Data models.

We keep things simple with a single dataclass, `Item`, representing one
collected signal (a news article, press release, restructuring event, etc.).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Allowed signal types (kept in sync with the README and classifier).
SIGNAL_TYPES = (
    "job_posting",
    "layoff",
    "restructuring",
    "hiring_freeze",
    "skills_shortage",
    "labour_market_news",
    "unknown",
)


def _utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def make_hash(title: str, url: str) -> str:
    """
    Build a stable content hash used for deduplication.

    We combine the normalised title and url. If two items share either the same
    url or the same hash, they are considered duplicates.
    """
    normalized = f"{(title or '').strip().lower()}|{(url or '').strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class Item:
    """One collected job-market / labour signal."""

    source_type: str          # e.g. "rss", "company_news", "eurofound", "eures"
    source_name: str          # e.g. "Google News: Sweden layoffs", "Ericsson"
    title: str
    url: str
    published_at: str | None = None          # ISO string if known, else None
    collected_at: str = field(default_factory=_utcnow_iso)
    country: str | None = None
    company: str | None = None
    sector: str | None = None
    signal_type: str = "unknown"
    summary: str | None = None
    raw_text: str | None = None
    hash: str = ""
    id: int | None = None                    # set by the database after insert

    def __post_init__(self) -> None:
        # Always compute the hash from title + url if not provided.
        if not self.hash:
            self.hash = make_hash(self.title, self.url)

    def to_row(self) -> dict:
        """Convert to a dict matching the `items` table columns."""
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "collected_at": self.collected_at,
            "country": self.country,
            "company": self.company,
            "sector": self.sector,
            "signal_type": self.signal_type,
            "summary": self.summary,
            "raw_text": self.raw_text,
            "hash": self.hash,
        }
