# EU Job Market Radar

A small **agentic workflow** that tracks European job-market trends — layoffs,
restructuring, hiring freezes, skills shortages, and emerging roles — and emails
you a concise **weekly markdown report every Friday**.

It is built as a beginner-friendly learning project using **plain Python**: no
frontend, no dashboard, no vector database, no heavy frameworks.

---

## 1. What this project does

Each run, the radar:

1. **Collects** public job-market signals from:
   - Google News RSS searches (layoffs, hiring freezes, skills shortages, AI jobs, etc.)
   - Optional direct RSS feeds you add
   - Company newsrooms (Ericsson, Spotify, SAP, Nokia, … — easy to extend)
   - **National job boards (real vacancies)**, one collector per country:
     - 🇸🇪 Sweden — Arbetsförmedlingen open API (works out of the box)
     - 🇩🇪 Germany — Bundesagentur für Arbeit open API (works out of the box)
     - 🇫🇷 France — France Travail API (optional; needs free credentials)
     - 🇳🇱 Netherlands, 🇫🇮 Finland, 🇪🇸 Spain — safe placeholders with TODOs
       (no clean free national API yet; return nothing, never crash)
   - **Adzuna** — free multi-country job aggregator (optional key) covering
     Netherlands, Spain, France, Italy, Poland, Austria
   - **Cedefop Labour & Skills Shortage Index** — the official EU dataset of
     shortage occupations by country, parsed into the report's skills section
   - Eurofound European Restructuring Monitor (best-effort, polite)
   - EURES (safe placeholder — see TODOs)

> ℹ️ We deliberately **do not use Indeed**: it forbids scraping in its
> robots.txt/terms, blocks automated access, and no longer offers a public
> job-search API. Adzuna is the polite, sanctioned way to get similar breadth.
2. **Stores** every item in a local **SQLite** database (`data/radar.sqlite`).
3. **Deduplicates** by URL and content hash.
4. **Extracts metadata**: signal type, country, keywords.
5. **Generates** a weekly **markdown report** in `reports/`.
6. **Emails** the report to you over SMTP.
7. Runs locally **and** on **GitHub Actions** every Friday.

> ⚠️ This project deliberately **does not scrape LinkedIn**. It prefers RSS
> feeds, public pages, and public datasets, and it scrapes politely
> (robots.txt, rate limiting, descriptive User-Agent).

### Signal types

`job_posting`, `layoff`, `restructuring`, `hiring_freeze`, `skills_shortage`,
`labour_market_news`, `unknown`.

### Report sections

1. Executive summary
2. Layoff and restructuring signals
3. Hiring and job-market signals
4. Emerging roles and skills
5. Country spotlight
6. Underrepresented angles
7. What this means for HR / Talent / Workforce Planning
8. Sources reviewed

If no LLM key is configured, a **deterministic fallback** report is generated
(counts, top keywords, newest items, simple observations) so the project always
works without any paid API.

---

## 2. How to install locally

Requires **Python 3.11+**.

```bash
# 1. Go to the project folder
cd eu-job-market-radar

# 2. (Recommended) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

The `openai` and `anthropic` packages are listed but only used if you enable an
LLM. The project runs fine without ever calling them.

---

## 3. How to create `.env`

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Then edit `.env`. The `.env` file is git-ignored, so your secrets stay local.

---

## 4. How to run manually

```bash
# Full run: collect -> store -> report -> email (if configured)
python main.py --days 7

# Only collect & store items (no report, no email)
python main.py --collect-only

# Only (re)generate a report from items already stored
python main.py --report-only

# Force sending the email (requires SMTP settings)
python main.py --report-only --send-email

# Change the look-back window
python main.py --days 14
```

The generated report appears in `reports/radar-YYYY-MM-DD.md`.

A good first run: `python main.py --collect-only` to fill the database, then
`python main.py --report-only` to see a report — no email needed.

---

## 5. How to configure email

Set these variables in `.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=your.address@gmail.com
EMAIL_TO=where.to.send@example.com
```

If any of these are missing, the project **does not crash** — it prints a
warning and skips sending.

---

## 6. How to use Gmail SMTP (or another provider)

### Gmail

1. Enable **2-Step Verification** on your Google account.
2. Create an **App Password**:
   Google Account → Security → 2-Step Verification → App passwords.
3. Use that 16-character app password as `SMTP_PASSWORD` (not your normal
   password).
4. Settings:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   ```

### Other providers

The sender uses STARTTLS on the given port. Common settings:

| Provider     | SMTP_HOST              | SMTP_PORT |
|--------------|------------------------|-----------|
| Gmail        | smtp.gmail.com         | 587       |
| Outlook/365  | smtp.office365.com     | 587       |
| Fastmail     | smtp.fastmail.com      | 587       |
| Mailgun      | smtp.mailgun.org       | 587       |

Use whatever username/password your provider gives you.

---

## 7. How to set GitHub Secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add each of these (only email ones are required):

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`

Optional (for LLM summaries):

- `LLM_PROVIDER` (`openai`, `anthropic`, or leave unset for deterministic mode)
- `LLM_MODEL`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

---

## 8. How to enable GitHub Actions

1. Push this repo to GitHub (see the end of this README).
2. Go to the **Actions** tab and enable workflows if prompted.
3. The workflow `.github/workflows/weekly-radar.yml` runs automatically every
   Friday, and you can trigger it manually with **“Run workflow”**
   (workflow_dispatch).
4. After a run, the report is attached as a downloadable **artifact**
   (`weekly-report`), and emailed if SMTP secrets are set.

### ⏰ Time-zone note (important)

GitHub Actions cron is always in **UTC**. The workflow is scheduled at
**06:00 UTC** every Friday.

- **Friday 08:00 Europe/Stockholm ≈ 06:00 UTC in summer** (CEST, UTC+2)
- **Friday 08:00 Europe/Stockholm ≈ 07:00 UTC in winter** (CET, UTC+1)

So with `0 6 * * 5` the email arrives around **07:00–08:00 Stockholm time**
depending on daylight saving. Edit the cron in the workflow if you want a
different local time. (GitHub does not adjust for daylight saving, so the local
arrival time shifts by an hour across the year.)

---

## 9. How to add more RSS feeds or companies

Everything lives in **`config.py`**:

- **Google News queries** → add strings to `GOOGLE_NEWS_QUERIES`.
- **Direct RSS feeds** → add `(name, url)` tuples to `DIRECT_RSS_FEEDS`.
- **Companies** → add `(company_name, rss_url_or_None)` to `COMPANY_FEEDS`.
  Use `None` if you don't have a feed yet — it will be skipped safely.
- **Job-board search terms** → edit `JOB_SEARCH_TERMS` (used by every country
  collector) and `JOB_BOARD_LIMIT_PER_QUERY`.
- **Classification keywords** → edit `SIGNAL_KEYWORDS`.
- **Countries** → edit `COUNTRY_KEYWORDS`.
- **Keywords of interest** (for the report) → edit `EXTRA_KEYWORDS_OF_INTEREST`.

No code changes needed for any of these — just edit the lists.

### Country job-board collectors

Each country has its own file in `radar/collectors/` (`sweden_jobs.py`,
`germany_jobs.py`, `france_jobs.py`, `netherlands_jobs.py`, `finland_jobs.py`,
`spain_jobs.py`). Sweden and Germany work with no setup. To enable France, add
free credentials from https://francetravail.io/ to your `.env` / GitHub
secrets:

```
FRANCE_TRAVAIL_CLIENT_ID=...
FRANCE_TRAVAIL_CLIENT_SECRET=...
```

To add a new country, copy `sweden_jobs.py`, point it at that country's public
API, set `country="..."`, and register it in the `COLLECTORS` list in `main.py`.
The Netherlands/Finland/Spain files are placeholders with TODOs showing where
to start.

---

## 10. Limitations and ethical scraping notes

- **No LinkedIn scraping.** By design.
- **Polite by default**: descriptive User-Agent, per-host rate limiting
  (`REQUEST_DELAY_SECONDS`), request timeouts, and robots.txt checks for HTML
  scraping (`RESPECT_ROBOTS_TXT`).
- **Eurofound ERM** and **EURES** collectors are intentionally conservative.
  EURES is a safe placeholder returning no items; Eurofound is best-effort and
  returns nothing if the page structure is uncertain. See the TODOs in
  `radar/collectors/eurofound_collector.py` and `eures_collector.py`.
- **Classification is rule-based** (simple keyword matching). It will
  mis-classify some items. Tune the keyword lists in `config.py` to improve it.
- **Google News RSS** content and availability can change; treat results as
  signal, not ground truth.
- Respect the **terms of service** of any source you add, and don't increase
  request rates aggressively.

---

## Project structure

```
eu-job-market-radar/
  main.py                 # orchestration + CLI
  config.py               # all settings, sources, keywords
  radar/
    db.py                 # SQLite storage
    models.py             # Item dataclass + hashing
    collectors/           # rss / eurofound / eures / company_news
    processing/           # dedupe / keyword_extractor / classifier
    reporting/            # report_generator / email_sender
    utils/                # logging / http (polite requests)
  data/                   # SQLite db (git-ignored)
  reports/                # generated markdown reports (git-ignored)
  .github/workflows/      # weekly GitHub Actions schedule
```

---

## Pushing to GitHub & scheduling the Friday email

```bash
cd eu-job-market-radar
git init
git add .
git commit -m "Initial commit: EU Job Market Radar"
git branch -M main
git remote add origin https://github.com/<your-username>/eu-job-market-radar.git
git push -u origin main
```

Then:

1. Add the GitHub Secrets (section 7).
2. Enable Actions (section 8).
3. Done — you'll get the report every Friday morning.

Happy radar-ing! 📡
