"""
EURES collector (European job mobility portal).

EURES exposes job vacancies across the EU. Programmatic access generally goes
through an official API / dataset rather than scraping the search UI, and the
public HTML is heavily JavaScript-driven, which BeautifulSoup cannot render.

To stay polite and avoid brittle scraping, this is a *safe placeholder*: it
returns no items by default and never crashes. The structure is in place so you
can plug in a real source later.

TODO (improvements for the curious):
- Look into the EURES / EU Open Data portal datasets for job vacancies:
  https://data.europa.eu/  (search "EURES" or "job vacancies")
- If an official EURES API is available, call it here with proper auth and map
  each vacancy onto an Item with signal_type="job_posting", country=..., etc.
- Respect any API rate limits and terms of use.
"""

from __future__ import annotations

import config  # noqa: F401  (kept for when a real endpoint is wired in)
from radar.models import Item  # noqa: F401  (used once real parsing is added)
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def collect() -> list[Item]:
    # Placeholder: returns nothing for now. See module docstring TODOs.
    logger.info(
        "EURES collector is a safe placeholder (returns 0 items). "
        "See TODOs in eures_collector.py to wire in a real source."
    )
    return []
