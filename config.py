"""
Central configuration for EU Job Market Radar.

Everything that you might want to tweak (data sources, keywords, country list,
LLM settings, email settings) lives here so beginners only have to look in one
place to customise the project.

Secrets (SMTP password, API keys) are read from environment variables, which
are loaded from a local ".env" file via python-dotenv.
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file in the project root (if present).
load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DOCS_DIR = BASE_DIR / "docs"
DB_PATH = DATA_DIR / "radar.sqlite"
# The daily public snapshot consumed by the website (committed/pushed to the site).
DATA_JSON_PATH = DOCS_DIR / "data.json"

# Make sure the folders exist (cheap and safe to call on every run).
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

# ISO-2 country codes for the website (flags / labels).
COUNTRY_CODES = {
    "Sweden": "SE", "Denmark": "DK", "Norway": "NO", "Finland": "FI",
    "Germany": "DE", "Netherlands": "NL", "France": "FR", "Italy": "IT",
    "Spain": "ES", "Poland": "PL", "Ireland": "IE", "Belgium": "BE",
    "Austria": "AT", "Switzerland": "CH", "EU": "EU", "Europe": "EU",
}

# ---------------------------------------------------------------------------
# HTTP / politeness settings
# ---------------------------------------------------------------------------
# A descriptive User-Agent is good manners: it tells site owners who is making
# requests and gives them a way to contact you.
USER_AGENT = (
    "eu-job-market-radar/1.0 (personal learning project; "
    "+https://github.com/your-username/eu-job-market-radar)"
)
# Seconds to wait between requests to the SAME host (simple rate limiting).
REQUEST_DELAY_SECONDS = 2.0
# Per-request network timeout in seconds.
REQUEST_TIMEOUT_SECONDS = 20
# Whether to check robots.txt before scraping HTML pages.
RESPECT_ROBOTS_TXT = True

# ---------------------------------------------------------------------------
# Google News RSS search queries
# ---------------------------------------------------------------------------
# Each query becomes a Google News RSS feed. Google News exposes search results
# as RSS, which is allowed and far friendlier than scraping HTML.
GOOGLE_NEWS_QUERIES = [
    "Europe layoffs",
    "EU layoffs",
    "Europe job cuts",
    "Europe redundancies",
    "Sweden layoffs",
    "Denmark layoffs",
    "Germany layoffs",
    "Netherlands layoffs",
    "France layoffs",
    "Italy layoffs",
    "Spain layoffs",
    "Europe hiring freeze",
    "Europe restructuring",
    "EU skills shortage",
    "AI jobs Europe",
    "AI governance jobs Europe",
    "workforce planning Europe",
    "HR analytics Europe",
    "talent management Europe",
]

# Google News RSS endpoint. {query} is URL-encoded by the collector.
# hl = language, gl = country, ceid = country:language edition.
GOOGLE_NEWS_RSS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
)

# ---------------------------------------------------------------------------
# Generic / direct RSS feeds (non-Google).
# Add any public RSS feed about labour markets, HR, or the economy here.
# ---------------------------------------------------------------------------
DIRECT_RSS_FEEDS = [
    # (source_name, url)
    # Example placeholders — uncomment / replace with feeds you trust:
    # ("Euractiv Economy", "https://www.euractiv.com/sections/economy-jobs/feed/"),
    # ("ECB Press", "https://www.ecb.europa.eu/rss/press.html"),
]

# ---------------------------------------------------------------------------
# Company newsrooms / press release feeds.
# Many large companies publish an RSS feed or a press page. Where a public RSS
# feed is known it is listed; otherwise the URL is left as None with a TODO so
# the collector simply skips it without crashing.
# ---------------------------------------------------------------------------
COMPANY_FEEDS = [
    # (company_name, rss_url_or_None)
    ("Ericsson", "https://www.ericsson.com/en/rss"),
    ("Spotify", "https://newsroom.spotify.com/feed/"),
    ("SAP", "https://news.sap.com/feed/"),
    ("Nokia", "https://www.nokia.com/rss.xml"),
    # TODO: confirm/replace the feeds below — left as None so they skip safely.
    ("IKEA", None),            # TODO: find a public Inter IKEA / IKEA newsroom RSS
    ("Volvo Group", None),     # TODO: Volvo Group media RSS
    ("Klarna", None),          # TODO: Klarna newsroom RSS
    ("Siemens", None),         # TODO: Siemens press RSS
    ("Maersk", None),          # TODO: Maersk press RSS
    ("Novo Nordisk", None),    # TODO: Novo Nordisk news RSS
]

# ---------------------------------------------------------------------------
# Eurofound European Restructuring Monitor (ERM)
# ---------------------------------------------------------------------------
EUROFOUND_ERM_URL = "https://www.eurofound.europa.eu/en/restructuring/erm"

# ---------------------------------------------------------------------------
# EURES (European job mobility portal)
# ---------------------------------------------------------------------------
EURES_URL = "https://eures.europa.eu/index_en"

# ---------------------------------------------------------------------------
# Country job-board collectors.
#
# Each country has its own collector file in radar/collectors/. They all use
# the SAME English search terms below, so coverage stays consistent and easy
# to tune in one place. Job titles returned by national APIs are in the local
# language (we do not translate them), but everything we control is in English.
#
# Keep the limit modest so a weekly run does not flood the database with
# thousands of vacancies.
# ---------------------------------------------------------------------------
JOB_SEARCH_TERMS = [
    "AI",
    "machine learning",
    "data scientist",
    "data engineer",
    "workforce planning",
    "HR analytics",
    "people analytics",
    "talent acquisition",
]
JOB_BOARD_LIMIT_PER_QUERY = 15

# --- Sweden: Arbetsförmedlingen JobTech API (public, no key required) ---
#   docs: https://jobtechdev.se/
SWEDEN_JOBS_API = "https://jobsearch.api.jobtechdev.se/search"

# --- Germany: Bundesagentur für Arbeit "Jobsuche" API (public app key) ---
# The key below is the well-known public key used by their own web/app client;
# no personal registration is required to read public vacancies.
GERMANY_JOBS_API = (
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
)
GERMANY_JOBS_API_KEY = "jobboerse-jobsuche"
# Public vacancy detail pages are built from the ad's reference number:
GERMANY_JOB_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

# --- France: France Travail "Offres d'emploi" API (free, but OAuth required) ---
# Create free credentials at https://francetravail.io/ and put them in your
# .env / GitHub secrets. If they are missing, the collector skips safely.
FRANCE_JOBS_TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
)
FRANCE_JOBS_API = (
    "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
)
FRANCE_TRAVAIL_CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID", "").strip()
FRANCE_TRAVAIL_CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET", "").strip()

# --- Adzuna: free job-search aggregator API covering many EU countries ------
# One collector (adzuna_jobs.py) covers several countries via this single API.
# Create free credentials at https://developer.adzuna.com/ and put them in your
# .env / GitHub secrets. If they are missing, the collector skips safely.
#
# Note: Adzuna does NOT cover Sweden or Finland. Sweden keeps its own native
# Arbetsförmedlingen collector; Germany already has a native collector, so it
# is left out of the Adzuna list below to avoid double-counting.
ADZUNA_API = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "").strip()
# Adzuna 2-letter country code -> display name used in our reports.
ADZUNA_COUNTRIES = {
    "nl": "Netherlands",
    "es": "Spain",
    "fr": "France",
    "it": "Italy",
    "pl": "Poland",
    "at": "Austria",
}

# ---------------------------------------------------------------------------
# Cedefop Labour and Skills Shortage Index (CLSSI) — the EU skills source.
# A public Excel dataset of labour/skills shortage scores (1=low .. 4=severe)
# by occupation group, with one sheet per country plus an EU27 sheet.
#   page:    https://www.cedefop.europa.eu/en/datasets/labour-skills-shortage-index
# The report downloads and parses this to show real shortage occupations.
# ---------------------------------------------------------------------------
CEDEFOP_CLSSI_URL = (
    "https://www.cedefop.europa.eu/files/"
    "2024_cedefop_labour_skills_shortage_index_clssi_dataset.xlsx"
)
# Map our country names to the CLSSI sheet codes we want to feature, plus EU27.
CEDEFOP_FEATURED = {
    "EU27": "EU27",
    "Sweden": "SE",
    "Germany": "DE",
    "Netherlands": "NL",
    "France": "FR",
    "Spain": "ES",
    "Italy": "IT",
    "Finland": "FI",
}
# Only occupations at or above this index count as a real shortage (1..4 scale).
CEDEFOP_SHORTAGE_THRESHOLD = 3.0

# ---------------------------------------------------------------------------
# GDELT — global news-event database (free, no key, fully sanctioned for
# programmatic use). It is TRANSLINGUAL: querying English layoff terms also
# matches LOCAL-LANGUAGE articles per country (e.g. German "Entlassungen"),
# giving far broader European coverage than English-only Google News.
#   docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
# ---------------------------------------------------------------------------
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "layoffs"            # single robust term; translingual broadens it
GDELT_TIMESPAN = "14d"
GDELT_LIMIT_PER_COUNTRY = 25
# FIPS 10-4 country codes (used by GDELT 'sourcecountry') -> our display names.
GDELT_COUNTRIES = {
    "GM": "Germany", "FR": "France", "IT": "Italy", "SP": "Spain",
    "SW": "Sweden", "NL": "Netherlands", "DA": "Denmark", "NO": "Norway",
    "FI": "Finland", "PL": "Poland", "BE": "Belgium", "AU": "Austria",
    "SZ": "Switzerland", "EI": "Ireland", "PO": "Portugal", "GR": "Greece",
}

# ---------------------------------------------------------------------------
# Arbeitnow — free, public, no-key job-board API (Europe-focused, many German
# and EU listings). https://www.arbeitnow.com/api/job-board-api
# ---------------------------------------------------------------------------
ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api"

# ---------------------------------------------------------------------------
# Classification keywords (lower-cased matching).
# Order matters: the classifier checks job_posting hints, then the categories
# below in this dictionary order.
# ---------------------------------------------------------------------------
SIGNAL_KEYWORDS = {
    "layoff": [
        "layoff", "layoffs", "lay off", "lay offs", "job cuts", "jobcuts",
        "redundancy", "redundancies", "dismissal", "dismissals",
        "workforce reduction", "cut jobs", "cutting jobs", "slash jobs",
        "axe jobs", "headcount reduction", "downsizing",
    ],
    "restructuring": [
        "restructuring", "restructure", "reorganization", "reorganisation",
        "reorganize", "reorganise", "transformation programme",
        "transformation program", "business transformation",
    ],
    "hiring_freeze": [
        "hiring freeze", "hiring freezes", "freeze hiring", "freezing hiring",
        "recruitment freeze", "pause hiring", "hiring pause",
    ],
    "skills_shortage": [
        "skills shortage", "skill shortage", "talent shortage",
        "labour shortage", "labor shortage", "skills gap", "skill gap",
        "talent gap",
    ],
    # labour_market_news is a catch-all for HR/analytics/AI-governance topics.
    "labour_market_news": [
        "ai governance", "ai jobs", "workforce planning", "hr analytics",
        "people analytics", "talent management", "labour market",
        "labor market", "employment report", "unemployment",
    ],
}

# Words that strongly suggest the item is an actual job posting (vacancy)
# rather than news about the labour market.
JOB_POSTING_HINTS = [
    "apply now", "we are hiring", "we're hiring", "job opening",
    "job vacancy", "vacancy", "open position", "open role", "join our team",
    "now hiring", "career opportunity",
]

# ---------------------------------------------------------------------------
# Country detection. Maps a canonical country label to keywords to search for.
# ---------------------------------------------------------------------------
COUNTRY_KEYWORDS = {
    "Sweden": ["sweden", "swedish", "stockholm"],
    "Denmark": ["denmark", "danish", "copenhagen"],
    "Norway": ["norway", "norwegian", "oslo"],
    "Finland": ["finland", "finnish", "helsinki"],
    "Germany": ["germany", "german", "berlin", "munich", "frankfurt"],
    "Netherlands": ["netherlands", "dutch", "amsterdam", "the hague"],
    "France": ["france", "french", "paris"],
    "Italy": ["italy", "italian", "rome", "milan"],
    "Spain": ["spain", "spanish", "madrid", "barcelona"],
    "Poland": ["poland", "polish", "warsaw"],
    "Ireland": ["ireland", "irish", "dublin"],
    "Belgium": ["belgium", "belgian", "brussels"],
    "Austria": ["austria", "austrian", "vienna"],
    "Switzerland": ["switzerland", "swiss", "zurich", "geneva"],
    # Broad fallbacks checked last.
    "EU": ["european union", "eu-wide", "eu "],
    "Europe": ["europe", "european"],
}

# Extra keywords surfaced in the "top keywords" section of the fallback report.
EXTRA_KEYWORDS_OF_INTEREST = [
    "ai", "artificial intelligence", "automation", "remote work",
    "return to office", "rto", "manufacturing", "tech", "banking",
    "automotive", "retail", "green jobs", "renewable", "semiconductor",
]

# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------
LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "none").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or "").strip()

# Sensible default models per provider.
DEFAULT_LLM_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6",
}


def get_llm_model() -> str:
    """Return the configured model, or a sensible default for the provider."""
    if LLM_MODEL:
        return LLM_MODEL
    return DEFAULT_LLM_MODELS.get(LLM_PROVIDER, "")


# ---------------------------------------------------------------------------
# Email settings
# ---------------------------------------------------------------------------
def _clean_credential(value: str) -> str:
    """
    Remove ALL whitespace (including non-breaking spaces, U+00A0) from a
    credential.

    Why: Gmail shows App Passwords grouped as "abcd efgh ijkl mnop", but the
    real password is 16 characters with no spaces. Copy-pasting often brings
    along regular or non-breaking spaces. A non-breaking space cannot even be
    ASCII-encoded for SMTP AUTH and would crash the login. SMTP usernames and
    app passwords never legitimately contain whitespace, so stripping it is
    safe and makes the project forgiving of this very common mistake.
    """
    cleaned = re.sub(r"\s+", "", value or "")
    if cleaned != (value or "").strip():
        # Don't log the secret itself — just that we cleaned it.
        print(
            "[config] Note: removed stray whitespace from an SMTP credential "
            "(e.g. spaces pasted from a Gmail App Password)."
        )
    return cleaned


SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = _clean_credential(os.getenv("SMTP_USER", ""))
SMTP_PASSWORD = _clean_credential(os.getenv("SMTP_PASSWORD", ""))
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()


def email_is_configured() -> bool:
    """True only if every required SMTP/email field is present."""
    return all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO])
