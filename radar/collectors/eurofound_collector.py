"""
Eurofound European Restructuring Monitor (ERM) collector.

The ERM publishes restructuring "events" (announced layoffs, plant closures,
expansions, etc.) across the EU. There is a public web interface, but at the
time of writing there is no simple, stable public RSS/JSON endpoint that is
guaranteed to be scrape-friendly.

This collector therefore does a *best-effort, polite* attempt:
- It checks robots.txt first.
- It fetches the ERM landing page and looks for obvious article/event links.
- If anything is uncertain or fails, it returns an empty list (never crashes).

TODO (improvements for the curious):
- Investigate the ERM factsheet/event API or downloadable datasets:
  https://www.eurofound.europa.eu/en/restructuring/european-restructuring-monitor
- If a stable dataset/RSS becomes available, parse that instead of HTML.
- Map ERM fields (company, country, jobs affected, event type) onto Item fields
  (company, country, signal_type=restructuring/layoff, summary).
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from radar.models import Item
from radar.utils.http import get
from radar.utils.logging import get_logger

logger = get_logger(__name__)


def collect() -> list[Item]:
    items: list[Item] = []

    resp = get(config.EUROFOUND_ERM_URL, check_robots=True)
    if resp is None:
        logger.info("Eurofound ERM not reachable / disallowed — returning 0 items")
        return items

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        logger.warning("Failed to parse Eurofound HTML: %s", exc)
        return items

    # Best-effort: collect links that look like restructuring articles/events.
    # The exact markup may change; we keep this loose and safe.
    seen_links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        text = anchor.get_text(strip=True)
        if not text or len(text) < 15:
            continue
        # Heuristic: only keep links that mention restructuring-related slugs.
        if not any(slug in href.lower() for slug in ("restructuring", "/erm", "event")):
            continue
        full_url = urljoin(config.EUROFOUND_ERM_URL, href)
        if full_url in seen_links:
            continue
        seen_links.add(full_url)
        items.append(
            Item(
                source_type="eurofound",
                source_name="Eurofound ERM",
                title=text,
                url=full_url,
                signal_type="restructuring",  # ERM is restructuring-focused
                summary=text,
                raw_text=text,
            )
        )

    # Be conservative: if we somehow grabbed a huge number of nav links,
    # it's probably noise rather than events — return nothing rather than spam.
    if len(items) > 60:
        logger.info(
            "Eurofound parse looked like navigation noise (%d links) — discarding",
            len(items),
        )
        return []

    logger.info("Eurofound collector produced %d items (best-effort)", len(items))
    return items
