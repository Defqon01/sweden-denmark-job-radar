"""
Netherlands job-board collector.

Status: safe placeholder. At the time of writing there is no clean, free,
public job-vacancy API for the Netherlands that we can use politely without
scraping (the national portal werk.nl has no open API, and other aggregators
block automated access).

This collector therefore returns nothing and never crashes, keeping the run
healthy. The structure is here so a real source can be plugged in later.

TODO (improvements for the curious):
- Investigate UWV / werk.nl open data on https://data.overheid.nl/
- If an official open vacancy API appears, query it here and map each vacancy
  onto an Item with country="Netherlands", signal_type="job_posting".
- Reuse the English search terms in config.JOB_SEARCH_TERMS for consistency.
"""

from __future__ import annotations

from radar.models import Item  # noqa: F401  (used once a real source is added)
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def collect() -> list[Item]:
    logger.info(
        "Netherlands collector is a safe placeholder (0 items). "
        "See TODOs in netherlands_jobs.py."
    )
    return []
