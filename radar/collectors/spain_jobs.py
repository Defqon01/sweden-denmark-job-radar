"""
Spain job-board collector.

Status: safe placeholder. Spain's public employment service (SEPE) and the
Empléate portal do not expose a clean, free, public vacancy API that we can
query politely without scraping rendered web pages.

This collector returns nothing and never crashes. The structure is here so a
real source can be plugged in later.

TODO (improvements for the curious):
- Check the Spanish open-data portal https://datos.gob.es/ for vacancy
  datasets, and regional services (e.g. some autonomous communities publish
  open data).
- If an official open API appears, query it here and map each vacancy onto an
  Item with country="Spain", signal_type="job_posting", reusing
  config.JOB_SEARCH_TERMS.
"""

from __future__ import annotations

from radar.models import Item  # noqa: F401  (used once a real source is added)
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def collect() -> list[Item]:
    logger.info(
        "Spain collector is a safe placeholder (0 items). "
        "See TODOs in spain_jobs.py."
    )
    return []
