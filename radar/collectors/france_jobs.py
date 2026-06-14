"""
France job-board collector.

Source: France Travail (formerly Pôle emploi) "Offres d'emploi" API. This is a
free, official API, but unlike Sweden/Germany it requires OAuth credentials.

To enable it:
1. Create a free account and an application at https://francetravail.io/
2. Subscribe the application to the "Offres d'emploi v2" API.
3. Put the credentials in your .env / GitHub secrets:
     FRANCE_TRAVAIL_CLIENT_ID=...
     FRANCE_TRAVAIL_CLIENT_SECRET=...

If the credentials are missing, this collector skips safely and returns
nothing — it never crashes the run.

Job titles come back in French — we do not translate them.
"""

from __future__ import annotations

import requests

import config
from radar.models import Item
from radar.utils.logging import get_logger

logger = get_logger(__name__)

SOURCE_NAME = "France Travail (France)"
# Scope required to read public job offers.
_SCOPE = "api_offresdemploiv2 o2dsoffre"


def _get_access_token() -> str | None:
    """Fetch an OAuth access token, or None on any problem."""
    try:
        resp = requests.post(
            config.FRANCE_JOBS_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": config.FRANCE_TRAVAIL_CLIENT_ID,
                "client_secret": config.FRANCE_TRAVAIL_CLIENT_SECRET,
                "scope": _SCOPE,
            },
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except (requests.RequestException, ValueError) as exc:
        logger.warning("France: could not get access token: %s", exc)
        return None


def _offer_to_item(offer: dict) -> Item | None:
    """Convert one France Travail offer into an Item, or None if unusable."""
    title = (offer.get("intitule") or "").strip()
    offer_id = (offer.get("id") or "").strip()
    if not title or not offer_id:
        return None

    # Prefer the official origin URL; fall back to the candidate detail page.
    url = ((offer.get("origineOffre") or {}).get("urlOrigine") or "").strip()
    if not url:
        url = f"https://candidat.francetravail.fr/offres/recherche/detail/{offer_id}"

    employer = ((offer.get("entreprise") or {}).get("nom") or "").strip() or None
    location = (offer.get("lieuTravail") or {}).get("libelle", "")
    summary = (location or "").strip() or None

    return Item(
        source_type="job_board",
        source_name=SOURCE_NAME,
        title=title,
        url=url,
        published_at=(offer.get("dateCreation") or None),
        country="France",
        company=employer,
        signal_type="job_posting",
        summary=summary,
        raw_text=summary,
    )


def collect() -> list[Item]:
    if not (config.FRANCE_TRAVAIL_CLIENT_ID and config.FRANCE_TRAVAIL_CLIENT_SECRET):
        logger.info(
            "France: no France Travail credentials set — skipping safely. "
            "See france_jobs.py to enable."
        )
        return []

    token = _get_access_token()
    if not token:
        return []

    items: list[Item] = []
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": config.USER_AGENT,
        "Accept": "application/json",
    }
    limit = config.JOB_BOARD_LIMIT_PER_QUERY
    for term in config.JOB_SEARCH_TERMS:
        # "range" is 0-indexed inclusive, e.g. "0-14" returns 15 offers.
        params = {"motsCles": term, "range": f"0-{max(0, limit - 1)}"}
        try:
            resp = requests.get(
                config.FRANCE_JOBS_API,
                params=params,
                headers=headers,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            # 204 = no results for this query; treat as empty, not an error.
            if resp.status_code == 204:
                offers = []
            else:
                resp.raise_for_status()
                offers = resp.json().get("resultats") or []
        except (requests.RequestException, ValueError) as exc:
            logger.warning("France: request failed for '%s': %s", term, exc)
            continue

        logger.info("France '%s': %d offer(s)", term, len(offers))
        for offer in offers:
            item = _offer_to_item(offer)
            if item:
                items.append(item)

    logger.info("France collector produced %d items", len(items))
    return items
