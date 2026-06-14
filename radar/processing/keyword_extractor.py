"""
Very small keyword extractor.

Given some text, return which of our "keywords of interest" appear in it. This
is intentionally simple (substring matching on a configurable list) — no NLP
libraries, no vector database, just transparent rules a beginner can follow.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

import config


def _haystack(*texts: str | None) -> str:
    """Join provided texts into one lower-cased string for matching."""
    return " ".join(t for t in texts if t).lower()


@lru_cache(maxsize=256)
def _keyword_pattern(keyword: str) -> re.Pattern:
    """
    Compile a word-boundary regex for a keyword.

    Word boundaries stop short tokens like "ai" or "rto" from matching inside
    unrelated words (e.g. "Spain", "training"). Multi-word phrases still match
    as a phrase.
    """
    return re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")


def extract_keywords(title: str | None, text: str | None = None) -> list[str]:
    """Return the keywords of interest found in the title/text."""
    haystack = _haystack(title, text)
    found = []
    for kw in config.EXTRA_KEYWORDS_OF_INTEREST:
        if _keyword_pattern(kw).search(haystack):
            found.append(kw)
    return found


def top_keywords(items: list[dict], limit: int = 10) -> list[tuple[str, int]]:
    """
    Count keyword occurrences across many items (dict rows from the DB).

    Returns a list of (keyword, count) sorted by count descending.
    """
    counter: Counter[str] = Counter()
    for item in items:
        for kw in extract_keywords(item.get("title"), item.get("summary")):
            counter[kw] += 1
    return counter.most_common(limit)
