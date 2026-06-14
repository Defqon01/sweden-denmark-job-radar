"""
Rule-based classification.

Two jobs:
1. `classify_signal` — decide the signal_type from title/text keywords.
2. `detect_country`  — guess a country from title/text keywords.

Everything is simple, deterministic substring matching driven by the lists in
config.py, so behaviour is easy to predict and tweak.
"""

from __future__ import annotations

import config


def _haystack(*texts: str | None) -> str:
    return " ".join(t for t in texts if t).lower()


def _looks_like_job_posting(haystack: str) -> bool:
    return any(hint in haystack for hint in config.JOB_POSTING_HINTS)


def classify_signal(title: str | None, text: str | None = None) -> str:
    """
    Return one of the signal types defined in config.SIGNAL_KEYWORDS,
    or "job_posting" / "unknown".

    Rules (in priority order):
    - layoff keywords      -> layoff
    - restructuring        -> restructuring
    - hiring freeze        -> hiring_freeze
    - skills shortage      -> skills_shortage
    - labour-market topics -> labour_market_news, UNLESS it looks like an
                              actual vacancy, in which case -> job_posting
    - nothing matched      -> unknown
    """
    haystack = _haystack(title, text)
    if not haystack.strip():
        return "unknown"

    # Check the strong categories first, in the order defined in config.
    for signal_type, keywords in config.SIGNAL_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            # Special case: labour_market_news items that are clearly vacancies
            # should be reclassified as job postings.
            if signal_type == "labour_market_news" and _looks_like_job_posting(haystack):
                return "job_posting"
            return signal_type

    # No category keyword matched. If it reads like a vacancy, call it a posting.
    if _looks_like_job_posting(haystack):
        return "job_posting"

    return "unknown"


def detect_country(title: str | None, text: str | None = None) -> str | None:
    """
    Return the first matching country label, or None.

    Specific countries are checked before the broad "EU"/"Europe" fallbacks
    because they are listed first in config.COUNTRY_KEYWORDS.
    """
    haystack = _haystack(title, text)
    if not haystack.strip():
        return None

    for country, keywords in config.COUNTRY_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return country
    return None


def enrich_item(item) -> None:
    """
    Fill in signal_type and country on an Item in place, using its title and
    any summary/raw_text available.
    """
    text = item.summary or item.raw_text
    if item.signal_type in (None, "", "unknown"):
        item.signal_type = classify_signal(item.title, text)
    if not item.country:
        item.country = detect_country(item.title, text)
