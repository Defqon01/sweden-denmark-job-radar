"""
Deduplication.

Two levels of protection:
1. In-memory dedupe within a single collection run (by url and by content hash).
2. The database also enforces a UNIQUE constraint on `hash` and we check the
   url against already-stored items.

This module handles level 1 plus a helper to filter out items already in the DB.
"""

from __future__ import annotations

from radar.db import get_connection, hash_exists, url_exists
from radar.models import Item
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def dedupe_in_memory(items: list[Item]) -> list[Item]:
    """Remove duplicates within a single list, by url then by content hash."""
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    unique: list[Item] = []

    for item in items:
        url_key = (item.url or "").strip().lower()
        if url_key and url_key in seen_urls:
            continue
        if item.hash in seen_hashes:
            continue
        seen_urls.add(url_key)
        seen_hashes.add(item.hash)
        unique.append(item)

    removed = len(items) - len(unique)
    if removed:
        logger.info("Removed %d in-memory duplicate(s)", removed)
    return unique


def filter_already_stored(items: list[Item]) -> list[Item]:
    """Drop items whose url or hash already exists in the database."""
    conn = get_connection()
    fresh: list[Item] = []
    try:
        for item in items:
            if item.url and url_exists(conn, item.url):
                continue
            if hash_exists(conn, item.hash):
                continue
            fresh.append(item)
    finally:
        conn.close()

    removed = len(items) - len(fresh)
    if removed:
        logger.info("Skipped %d item(s) already in the database", removed)
    return fresh
