"""
Polite HTTP helpers.

Goals:
- Always send a descriptive User-Agent header.
- Rate-limit requests per host so we never hammer a server.
- Optionally honour robots.txt before scraping HTML.
- Never raise on network errors — return None and log instead, so a single
  failing source can't crash the whole run.
"""

from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

import config
from radar.utils.logging import get_logger

logger = get_logger(__name__)

# Remember the last time we hit each host, to space out requests.
_last_request_time: dict[str, float] = {}

# Cache robots.txt parsers per host so we only fetch them once.
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _host_of(url: str) -> str:
    return urlparse(url).netloc


def _respect_rate_limit(host: str) -> None:
    """Sleep if we contacted this host very recently."""
    now = time.monotonic()
    last = _last_request_time.get(host)
    if last is not None:
        elapsed = now - last
        wait = config.REQUEST_DELAY_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)
    _last_request_time[host] = time.monotonic()


def _can_fetch(url: str) -> bool:
    """Return True if robots.txt allows fetching this URL (best-effort)."""
    if not config.RESPECT_ROBOTS_TXT:
        return True

    host = _host_of(url)
    parser = _robots_cache.get(host)

    if host not in _robots_cache:
        parser = urllib.robotparser.RobotFileParser()
        robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
        try:
            # Use requests (with our UA) to fetch, then feed lines to the parser.
            resp = requests.get(
                robots_url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            else:
                # No robots.txt (or not readable) => assume allowed.
                parser = None
        except requests.RequestException:
            # If we can't read robots.txt, fail open but log it.
            logger.debug("Could not fetch robots.txt for %s", host)
            parser = None
        _robots_cache[host] = parser

    if parser is None:
        return True
    return parser.can_fetch(config.USER_AGENT, url)


def get(
    url: str,
    *,
    check_robots: bool = False,
    extra_headers: dict | None = None,
) -> requests.Response | None:
    """
    Perform a polite GET request.

    extra_headers, if given, are merged on top of the default User-Agent header
    (useful for APIs that require a key header).

    Returns the Response on success, or None on any failure (network error,
    disallowed by robots.txt, non-200 status). Never raises.
    """
    host = _host_of(url)

    if check_robots and not _can_fetch(url):
        logger.warning("robots.txt disallows fetching %s — skipping", url)
        return None

    _respect_rate_limit(host)

    headers = {"User-Agent": config.USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)

    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None
