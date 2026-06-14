"""
SQLite persistence layer.

Uses only the standard-library `sqlite3` module. Two tables:
- items:   every collected signal
- reports: one row per generated weekly report

The functions here are deliberately small and explicit so a beginner can
follow exactly what SQL runs.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from radar.models import Item
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create tables and indexes if they don't exist yet."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type   TEXT,
                source_name   TEXT,
                title         TEXT,
                url           TEXT,
                published_at  TEXT,
                collected_at  TEXT,
                country       TEXT,
                company       TEXT,
                sector        TEXT,
                signal_type   TEXT,
                summary       TEXT,
                raw_text      TEXT,
                hash          TEXT UNIQUE
            );

            CREATE INDEX IF NOT EXISTS idx_items_url ON items(url);
            CREATE INDEX IF NOT EXISTS idx_items_hash ON items(hash);
            CREATE INDEX IF NOT EXISTS idx_items_collected ON items(collected_at);

            CREATE TABLE IF NOT EXISTS reports (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date  TEXT,
                report_path  TEXT,
                created_at   TEXT,
                sent_email   INTEGER DEFAULT 0
            );
            """
        )
        conn.commit()
        logger.info("Database initialised at %s", db_path or config.DB_PATH)
    finally:
        conn.close()


def url_exists(conn: sqlite3.Connection, url: str) -> bool:
    """Return True if an item with this exact url already exists."""
    cur = conn.execute("SELECT 1 FROM items WHERE url = ? LIMIT 1", (url,))
    return cur.fetchone() is not None


def hash_exists(conn: sqlite3.Connection, content_hash: str) -> bool:
    """Return True if an item with this content hash already exists."""
    cur = conn.execute("SELECT 1 FROM items WHERE hash = ? LIMIT 1", (content_hash,))
    return cur.fetchone() is not None


def insert_item(conn: sqlite3.Connection, item: Item) -> bool:
    """
    Insert one item. Returns True if inserted, False if it was a duplicate.

    The UNIQUE constraint on `hash` is our last line of defence against
    duplicates even if the in-memory dedupe missed something.
    """
    row = item.to_row()
    try:
        conn.execute(
            """
            INSERT INTO items
                (source_type, source_name, title, url, published_at,
                 collected_at, country, company, sector, signal_type,
                 summary, raw_text, hash)
            VALUES
                (:source_type, :source_name, :title, :url, :published_at,
                 :collected_at, :country, :company, :sector, :signal_type,
                 :summary, :raw_text, :hash)
            """,
            row,
        )
        return True
    except sqlite3.IntegrityError:
        # Duplicate hash — silently skip.
        return False


def save_items(items: list[Item], db_path: Path | None = None) -> int:
    """Save a list of items, skipping duplicates. Returns count actually saved."""
    conn = get_connection(db_path)
    saved = 0
    try:
        for item in items:
            if insert_item(conn, item):
                saved += 1
        conn.commit()
    finally:
        conn.close()
    logger.info("Saved %d new items (out of %d collected)", saved, len(items))
    return saved


def get_recent_items(days: int = 7, db_path: Path | None = None) -> list[dict]:
    """Return items collected within the last `days` days, newest first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            SELECT * FROM items
            WHERE collected_at >= ?
            ORDER BY COALESCE(published_at, collected_at) DESC
            """,
            (cutoff,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def record_report(
    report_date: str,
    report_path: str,
    sent_email: bool = False,
    db_path: Path | None = None,
) -> int:
    """Insert a row in `reports` and return its new id."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO reports (report_date, report_path, created_at, sent_email)
            VALUES (?, ?, ?, ?)
            """,
            (
                report_date,
                report_path,
                datetime.now(timezone.utc).isoformat(),
                1 if sent_email else 0,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def mark_report_sent(report_id: int, db_path: Path | None = None) -> None:
    """Flag a report row as having been emailed successfully."""
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE reports SET sent_email = 1 WHERE id = ?", (report_id,))
        conn.commit()
    finally:
        conn.close()
