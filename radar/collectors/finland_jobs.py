"""
Finland job-board collector.

Status: safe placeholder. Finland's public employment service moved from the
old TE-palvelut open API to the new "Job Market Finland" (Työmarkkinatori)
platform, and a stable, documented open vacancy API was not confirmed at the
time of writing. The old endpoint now returns no usable data.

This collector returns nothing and never crashes. The structure is here so a
real source can be plugged in later.

TODO (improvements for the curious):
- Check Job Market Finland for an official open API:
  https://tyomarkkinatori.fi/en/
- Check the Finnish open-data portal https://www.avoindata.fi/ for vacancies.
- If found, query it here and map each vacancy onto an Item with
  country="Finland", signal_type="job_posting", reusing
  config.JOB_SEARCH_TERMS.
"""

from __future__ import annotations

from radar.models import Item  # noqa: F401  (used once a real source is added)
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def collect() -> list[Item]:
    logger.info(
        "Finland collector is a safe placeholder (0 items). "
        "See TODOs in finland_jobs.py."
    )
    return []
