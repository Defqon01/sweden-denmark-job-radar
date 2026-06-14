"""
EU Job Market Radar — entry point.

Orchestrates the whole weekly workflow:
1. Load config (done on import of `config`).
2. Initialise the database.
3. Run all collectors.
4. Classify + dedupe + save new items.
5. Generate the markdown report.
6. Optionally email it.
7. Record the report (and mark as sent if email succeeded).

CLI flags:
  --collect-only   Only collect & store items; skip report + email.
  --report-only    Only generate a report from items already stored; skip collecting.
  --send-email     Force an email send (otherwise email is sent only if configured).
  --days N         Look-back window for the report (default 7).

Run `python main.py --help` for details.
"""

from __future__ import annotations

import argparse
from datetime import date

import config
from radar import db
from radar.collectors import (
    adzuna_jobs,
    arbeitnow_collector,
    company_news_collector,
    eures_collector,
    eurofound_collector,
    finland_jobs,
    france_jobs,
    gdelt_collector,
    germany_jobs,
    netherlands_jobs,
    rss_collector,
    spain_jobs,
    sweden_jobs,
)
from radar.models import Item
from radar.processing import dedupe
from radar.processing.classifier import enrich_item
from radar.reporting import data_export, email_sender, report_generator
from radar.utils.logging import get_logger

logger = get_logger("main")

# The collectors to run, in order. Each must expose a `collect() -> list[Item]`.
COLLECTORS = [
    ("RSS / Google News", rss_collector.collect),
    ("GDELT news (multilingual)", gdelt_collector.collect),
    ("Company news", company_news_collector.collect),
    ("Sweden jobs", sweden_jobs.collect),
    ("Arbeitnow jobs", arbeitnow_collector.collect),
    ("Germany jobs", germany_jobs.collect),
    ("France jobs", france_jobs.collect),
    ("Netherlands jobs", netherlands_jobs.collect),
    ("Finland jobs", finland_jobs.collect),
    ("Spain jobs", spain_jobs.collect),
    ("Adzuna (multi-country jobs)", adzuna_jobs.collect),
    ("Eurofound ERM", eurofound_collector.collect),
    ("EURES", eures_collector.collect),
]


def run_collectors() -> list[Item]:
    """Run every collector, isolating failures so one bad source can't stop us."""
    all_items: list[Item] = []
    for name, collect_fn in COLLECTORS:
        logger.info("Running collector: %s", name)
        try:
            items = collect_fn()
            all_items.extend(items)
        except Exception as exc:  # defensive: never let one collector crash the run
            logger.error("Collector '%s' failed: %s", name, exc)
    logger.info("Collected %d raw item(s) in total", len(all_items))
    return all_items


def collect_and_store() -> int:
    """Collect, enrich, dedupe, and persist new items. Returns count saved."""
    items = run_collectors()

    # Enrich each item with signal_type + country before saving.
    for item in items:
        enrich_item(item)

    # Dedupe within this batch, then against what's already stored.
    items = dedupe.dedupe_in_memory(items)
    items = dedupe.filter_already_stored(items)

    saved = db.save_items(items)
    return saved


def build_and_maybe_send_report(days: int, force_send: bool) -> None:
    """Generate the report, save it, and email it if appropriate."""
    items = db.get_recent_items(days=days)
    logger.info("Generating report from %d item(s) (last %d days)", len(items), days)

    report_md = report_generator.generate_report(items, days=days)

    report_date = date.today().isoformat()
    report_path = config.REPORTS_DIR / f"radar-{report_date}.md"
    report_path.write_text(report_md, encoding="utf-8")
    logger.info("Report saved to %s", report_path)

    # Decide whether to send email.
    should_send = force_send or config.email_is_configured()
    sent = False
    if should_send:
        sent = email_sender.send_report(report_md, report_date)
    else:
        logger.info("Email not configured and --send-email not set — skipping send.")

    report_id = db.record_report(report_date, str(report_path), sent_email=sent)
    if sent:
        db.mark_report_sent(report_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EU Job Market Radar")
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect & store items; skip the report and email.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only generate the report from stored items; skip collecting.",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Force sending the report by email (requires SMTP settings).",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Generate the website's docs/data.json from stored items; skip email.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Look-back window in days for the report (default: 7).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("EU Job Market Radar starting (provider=%s)", config.LLM_PROVIDER)
    db.init_db()

    # Export-only: build data.json from already-stored items and stop.
    if args.export_json and args.report_only:
        data_export.export(days=args.days)
        return
    if args.export_json:
        # Collect fresh items first (unless report-only), then export.
        collect_and_store()
        data_export.export(days=args.days)
        logger.info("Done (data.json exported).")
        return

    if args.report_only:
        build_and_maybe_send_report(days=args.days, force_send=args.send_email)
        return

    saved = collect_and_store()
    logger.info("%d new item(s) stored.", saved)

    if args.collect_only:
        logger.info("--collect-only set: skipping report + email.")
        return

    build_and_maybe_send_report(days=args.days, force_send=args.send_email)
    logger.info("Done.")


if __name__ == "__main__":
    main()
