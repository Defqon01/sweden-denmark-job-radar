"""
Central configuration for the Sweden & Denmark Job Market Radar.

Everything you might want to tweak (data sources, keywords, country list, LLM
settings, email settings) lives here so there is only one place to look.

Secrets (SMTP password, API keys) are read from environment variables, loaded
from a local ".env" file via python-dotenv.

SCOPE: this radar deliberately covers ONLY Sweden and Denmark, so it can go deep
(native-language news, national job boards, country shortage + demand data)
instead of thin-and-wide across the EU.
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
# The public snapshot consumed by the website (committed/pushed to the site).
DATA_JSON_PATH = DOCS_DIR / "data.json"

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Scope — the single source of truth for which countries we cover.
# ---------------------------------------------------------------------------
FOCUS_COUNTRIES = ["Sweden", "Denmark"]

# ISO-2 country codes for the website (flags / labels).
COUNTRY_CODES = {"Sweden": "SE", "Denmark": "DK", "EU": "EU", "Europe": "EU"}

# Where a clickable vacancy count takes the reader: the live national job board,
# pre-filtered. {q} is replaced with a search term by the exporter.
VACANCY_BOARD_URLS = {
    "Sweden": "https://arbetsformedlingen.se/platsbanken/annonser?q={q}",
    "Denmark": "https://www.jobindex.dk/jobsoegning?q={q}",
}

# ---------------------------------------------------------------------------
# HTTP / politeness settings
# ---------------------------------------------------------------------------
USER_AGENT = (
    "sweden-denmark-job-radar/1.0 (personal project; "
    "+https://github.com/Defqon01/sweden-denmark-job-radar)"
)
REQUEST_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 20
RESPECT_ROBOTS_TXT = True

# ---------------------------------------------------------------------------
# Google News RSS — English-edition queries, scoped to Sweden + Denmark.
# ---------------------------------------------------------------------------
GOOGLE_NEWS_QUERIES = [
    "Sweden layoffs", "Sweden job cuts", "Sweden hiring freeze",
    "Sweden restructuring", "Sweden skills shortage",
    "Denmark layoffs", "Denmark job cuts", "Denmark hiring freeze",
    "Denmark restructuring", "Denmark skills shortage",
]
GOOGLE_NEWS_RSS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
)

# Native-language queries fetched from the LOCAL Google News edition — the big
# "local info" win, since most Swedish/Danish layoff news ("varsel", "fyringer")
# never reaches the English edition. Each entry carries the country it belongs
# to so items are attributed even when the headline never says Sweden/Denmark.
#   (query, hl, gl, ceid, country)
GOOGLE_NEWS_LOCAL_QUERIES = [
    # Swedish (sv-SE)
    ("varsel", "sv", "SE", "SE:sv", "Sweden"),
    ("uppsägningar", "sv", "SE", "SE:sv", "Sweden"),
    ("nedskärningar personal", "sv", "SE", "SE:sv", "Sweden"),
    ("konkurs anställda", "sv", "SE", "SE:sv", "Sweden"),
    ("anställningsstopp", "sv", "SE", "SE:sv", "Sweden"),
    ("kompetensbrist", "sv", "SE", "SE:sv", "Sweden"),
    ("omorganisation jobb", "sv", "SE", "SE:sv", "Sweden"),
    # Danish (da-DK)
    ("fyringer", "da", "DK", "DK:da", "Denmark"),
    ("afskedigelser", "da", "DK", "DK:da", "Denmark"),
    ("fyringsrunde", "da", "DK", "DK:da", "Denmark"),
    ("konkurs medarbejdere", "da", "DK", "DK:da", "Denmark"),
    ("ansættelsesstop", "da", "DK", "DK:da", "Denmark"),
    ("mangel på arbejdskraft", "da", "DK", "DK:da", "Denmark"),
    ("omstrukturering job", "da", "DK", "DK:da", "Denmark"),
]
GOOGLE_NEWS_RSS_TEMPLATE_LOCAL = (
    "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"
)

# ---------------------------------------------------------------------------
# Local Sweden/Denmark business & economy RSS feeds. (name, url, country).
# `country` pre-tags items so local-language headlines are attributed even when
# they never spell out the country. Unreachable feeds are skipped safely.
# ---------------------------------------------------------------------------
DIRECT_RSS_FEEDS = [
    # Sweden
    ("SVT Nyheter – Ekonomi", "https://www.svt.se/nyheter/ekonomi/rss.xml", "Sweden"),
    ("Dagens Nyheter – Ekonomi", "https://www.dn.se/ekonomi/rss/", "Sweden"),
    ("Breakit", "https://www.breakit.se/feed/artiklar", "Sweden"),
    # Denmark
    ("DR – Penge", "https://www.dr.dk/nyheder/service/feeds/penge", "Denmark"),
    ("DR – Indland", "https://www.dr.dk/nyheder/service/feeds/indland", "Denmark"),
    ("Finans.dk", "https://finans.dk/rss", "Denmark"),
]

# ---------------------------------------------------------------------------
# Major Swedish & Danish employer newsrooms (RSS where known, else None=skip).
# ---------------------------------------------------------------------------
COMPANY_FEEDS = [
    ("Ericsson", "https://www.ericsson.com/en/rss"),
    ("Spotify", "https://newsroom.spotify.com/feed/"),
    ("Volvo Cars", None),
    ("Klarna", None),
    ("IKEA", None),
    ("H&M", None),
    ("Maersk", None),
    ("Novo Nordisk", None),
    ("Carlsberg", None),
    ("Vestas", None),
    ("Ørsted", None),
    ("Danske Bank", None),
]

# Eurofound European Restructuring Monitor (EU-wide; yields SE/DK items too).
EUROFOUND_ERM_URL = "https://www.eurofound.europa.eu/en/restructuring/erm"

# ---------------------------------------------------------------------------
# Job-board collectors. Both countries use the same search terms so coverage
# stays consistent and the per-term counts double as a demand signal.
# ---------------------------------------------------------------------------
JOB_SEARCH_TERMS = [
    "AI", "machine learning", "data scientist", "data engineer",
    "software engineer", "nurse", "teacher", "electrician",
    "workforce planning", "HR analytics", "people analytics", "talent acquisition",
]
JOB_BOARD_LIMIT_PER_QUERY = 15

# Sweden: Arbetsförmedlingen JobTech API (public, no key). https://jobtechdev.se/
SWEDEN_JOBS_API = "https://jobsearch.api.jobtechdev.se/search"

# Denmark: Jobindex public search RSS (no key; intended for syndication).
DENMARK_JOBS_RSS = "https://www.jobindex.dk/jobsoegning.rss?q={query}"

# ---------------------------------------------------------------------------
# Cedefop Labour & Skills Shortage Index (CLSSI) — the shortage data source.
# Public Excel, one sheet per country (1=low .. 4=severe by occupation group).
# ---------------------------------------------------------------------------
CEDEFOP_CLSSI_URL = (
    "https://www.cedefop.europa.eu/files/"
    "2024_cedefop_labour_skills_shortage_index_clssi_dataset.xlsx"
)
# Only the two focus countries (+ EU27 for context).
CEDEFOP_FEATURED = {"EU27": "EU27", "Sweden": "SE", "Denmark": "DK"}
CEDEFOP_SHORTAGE_THRESHOLD = 3.0
CEDEFOP_LIMIT_PER_COUNTRY = 8

# ---------------------------------------------------------------------------
# GDELT — free, no-key, TRANSLINGUAL news-event database. An English "layoffs"
# query also matches Swedish/Danish coverage. Scoped to SE + DK source country.
# ---------------------------------------------------------------------------
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "layoffs"
GDELT_TIMESPAN = "30d"  # 30-day window for "biggest moves this month"
GDELT_LIMIT_PER_COUNTRY = 75
GDELT_COUNTRIES = {"SW": "Sweden", "DA": "Denmark"}

# ---------------------------------------------------------------------------
# Major employers that show up in Swedish/Danish workforce news. News items
# rarely carry a structured company, so the exporter scans HEADLINES for these
# to CLUSTER duplicate coverage of one layoff into a single event.
# ---------------------------------------------------------------------------
COMPANY_WATCHLIST = [
    # Sweden
    "Ericsson", "Volvo Cars", "Volvo Group", "Volvo", "Electrolux", "Klarna",
    "Spotify", "Northvolt", "Scania", "Sandvik", "Atlas Copco", "ABB", "SKF",
    "Saab", "Telia", "Tele2", "SEB", "Swedbank", "Handelsbanken", "H&M",
    "IKEA", "SAS", "Embracer", "King", "Truecaller", "Postnord", "PostNord",
    "ICA", "Coop", "Securitas", "Skanska", "NCC", "SJ", "Storytel", "Sinch",
    "Avanza", "Nordnet", "Husqvarna", "Assa Abloy", "Essity", "Boliden",
    # Denmark
    "Novo Nordisk", "Maersk", "Carlsberg", "Vestas", "Ørsted", "Danske Bank",
    "Pandora", "Lego", "Lundbeck", "Grundfos", "Danfoss", "Coloplast", "DSV",
    "Nordea", "GN Store Nord", "Demant", "Genmab", "Bang & Olufsen",
    "Rockwool", "ISS", "TDC", "Chr. Hansen", "Nilfisk", "Danish Crown",
    "Arla", "Salling Group", "Bestseller", "Jysk", "Ecco", "FLSmidth",
    "Topdanmark", "Tryg", "Velux", "Widex", "Nykredit", "Jyske Bank",
    # Global names that announce SE/DK cuts
    "Microsoft", "Google", "Meta", "Amazon", "Tesla", "Intel", "SAP", "IBM",
    "Nokia", "Tietoevry", "CGI", "Accenture", "Cognizant", "Siemens",
]

# ---------------------------------------------------------------------------
# Classification keywords (lower-cased). Order matters.
# ---------------------------------------------------------------------------
SIGNAL_KEYWORDS = {
    "layoff": [
        "layoff", "layoffs", "lay off", "lay offs", "job cuts", "jobcuts",
        "redundancy", "redundancies", "dismissal", "dismissals",
        "workforce reduction", "cut jobs", "cutting jobs", "slash jobs",
        "axe jobs", "headcount reduction", "downsizing",
        # Swedish
        "varsel", "varslar", "varslas", "varslade", "uppsäg", "säga upp",
        "sägs upp", "personalneddragning", "neddragning", "nedskärning",
        "permittering", "konkurs",
        # Danish
        "fyring", "fyrer", "fyret", "afskedig", "fyringsrunde", "massefyring",
        "nedskæring", "personalereduktion",
    ],
    "restructuring": [
        "restructuring", "restructure", "reorganization", "reorganisation",
        "reorganize", "reorganise", "transformation programme",
        "transformation program", "business transformation",
        "omstrukturering", "omorganisation", "omorganisering", "omstilling",
    ],
    "hiring_freeze": [
        "hiring freeze", "hiring freezes", "freeze hiring", "freezing hiring",
        "recruitment freeze", "pause hiring", "hiring pause",
        "anställningsstopp", "rekryteringsstopp", "ansættelsesstop",
    ],
    "skills_shortage": [
        "skills shortage", "skill shortage", "talent shortage",
        "labour shortage", "labor shortage", "skills gap", "skill gap",
        "talent gap",
        "kompetensbrist", "arbetskraftsbrist", "brist på arbetskraft",
        "mangel på arbejdskraft", "rekrutteringsudfordringer", "mangel på faglært",
    ],
    "labour_market_news": [
        "ai governance", "ai jobs", "workforce planning", "hr analytics",
        "people analytics", "talent management", "labour market",
        "labor market", "employment report", "unemployment",
    ],
}

JOB_POSTING_HINTS = [
    "apply now", "we are hiring", "we're hiring", "job opening",
    "job vacancy", "vacancy", "open position", "open role", "join our team",
    "now hiring", "career opportunity",
]

# Themes surfaced by the markdown report's keyword extractor (report path only;
# the website uses real vacancy-demand data instead of keyword guessing).
EXTRA_KEYWORDS_OF_INTEREST = [
    "ai", "artificial intelligence", "automation", "green jobs", "renewable",
    "semiconductor", "manufacturing", "tech", "banking", "automotive",
    "retail", "healthcare", "defence", "life sciences",
]

# ---------------------------------------------------------------------------
# Country detection — Sweden + Denmark only, with native spellings + big cities
# so local-language articles (which rarely say "Sweden"/"Denmark") still attach.
# Anything matching neither stays country=None and is dropped from the tiles.
# ---------------------------------------------------------------------------
COUNTRY_KEYWORDS = {
    "Sweden": [
        "sweden", "swedish", "sverige", "svensk", "svenska",
        "stockholm", "göteborg", "goteborg", "gothenburg", "malmö", "malmo",
        "uppsala", "västerås", "vasteras", "linköping", "linkoping", "örebro",
        "helsingborg", "norrköping", "norrkoping",
    ],
    "Denmark": [
        "denmark", "danish", "danmark", "dansk", "danske",
        "københavn", "kobenhavn", "copenhagen", "kbh",
        "aarhus", "århus", "odense", "aalborg", "ålborg", "esbjerg",
        "randers", "kolding", "vejle", "roskilde",
    ],
}

# City -> country gazetteer for the website's map clustering. The frontend holds
# the coordinates; this keeps the matching terms in one place.
SEDK_CITIES = {
    "Stockholm": "Sweden", "Göteborg": "Sweden", "Malmö": "Sweden",
    "Uppsala": "Sweden", "Västerås": "Sweden", "Linköping": "Sweden",
    "Örebro": "Sweden", "Helsingborg": "Sweden",
    "København": "Denmark", "Aarhus": "Denmark", "Odense": "Denmark",
    "Aalborg": "Denmark", "Esbjerg": "Denmark", "Roskilde": "Denmark",
}

# ---------------------------------------------------------------------------
# LLM settings — Anthropic Claude (Haiku) refines the narrative and translates
# Swedish/Danish headlines into plain English.
# ---------------------------------------------------------------------------
LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "none").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or "").strip()

DEFAULT_LLM_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
}


def get_llm_model() -> str:
    """Return the configured model, or a sensible default for the provider."""
    if LLM_MODEL:
        return LLM_MODEL
    return DEFAULT_LLM_MODELS.get(LLM_PROVIDER, "")


# ---------------------------------------------------------------------------
# Email settings (optional — the new version is a website, email is off unless
# SMTP is configured).
# ---------------------------------------------------------------------------
def _clean_credential(value: str) -> str:
    """Remove ALL whitespace from a credential (Gmail App Passwords paste with
    spaces / non-breaking spaces that would otherwise break SMTP AUTH)."""
    cleaned = re.sub(r"\s+", "", value or "")
    if cleaned != (value or "").strip():
        print("[config] Note: removed stray whitespace from an SMTP credential.")
    return cleaned


SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = _clean_credential(os.getenv("SMTP_USER", ""))
SMTP_PASSWORD = _clean_credential(os.getenv("SMTP_PASSWORD", ""))
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()


def email_is_configured() -> bool:
    return all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO])
