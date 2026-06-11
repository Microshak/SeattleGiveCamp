#!/usr/bin/env python3
"""
Seattle GiveCamp — Form Fillerouter (Sponsorship Form Agent)

Orchestrates:
  1. Read target companies from Google Sheet (Forms tab)
  2. Dedup against Tracking tab (skip already-submitted)
  3. For each company: navigate → find sponsorship form → fill via LLM → submit
  4. Record successful submissions in Tracking tab
  5. Log everything to SQLite
  6. Optionally email summary report

Usage:
  python main.py                  # Process all pending targets
  python main.py --dry-run        # Analyze but don't submit
  python main.py --company "Acme"  # Process a single company by name
  python main.py --url "https://..."  # Process a single URL
"""

import argparse
import logging
import sqlite3
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from config import Settings, load_settings
from form_filler import FormFiller, FormResult
from google_sheets import GoogleSheetsClient
from llm_client import LLMClient

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("formfillerouter")


# ── SQLite ───────────────────────────────────────────────────────────────
def init_db(db_path: str) -> sqlite3.Connection:
    """Create the submissions log table if it doesn't exist."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            company_url TEXT NOT NULL,
            status TEXT NOT NULL,
            form_purpose TEXT,
            form_url TEXT,
            error_message TEXT,
            screenshot_path TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def log_submission(conn: sqlite3.Connection, result: FormResult):
    """Insert a submission result into the SQLite log."""
    conn.execute("""
        INSERT INTO submissions (company_name, company_url, status, form_purpose,
                                  form_url, error_message, screenshot_path, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.company_name,
        result.company_url,
        result.status,
        result.form_purpose,
        result.form_url,
        result.error_message,
        result.screenshot_path,
        result.timestamp,
    ))
    conn.commit()


def send_summary_email(settings: Settings, results: list[FormResult]):
    """Send a summary email after a run."""
    if not settings.behavior.summary_email:
        return

    submitted = [r for r in results if r.status == "submitted"]
    skipped = [r for r in results if r.status in ("skipped", "requires_w9", "no_form_found")]
    errors = [r for r in results if r.status == "error"]

    body_parts = [
        f"Subject: FormFillerouter Run Summary — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Total companies processed: {len(results)}",
        f"  Successfully submitted: {len(submitted)}",
        f"  Skipped: {len(skipped)}",
        f"  Errors: {len(errors)}",
        "",
    ]

    if submitted:
        body_parts.append("--- Submitted ---")
        for r in submitted:
            body_parts.append(f"  ✓ {r.company_name} ({r.company_url}) — {r.form_purpose}")
        body_parts.append("")

    if skipped:
        body_parts.append("--- Skipped ---")
        for r in skipped:
            body_parts.append(f"  ⊘ {r.company_name} ({r.company_url}) — {r.status}: {r.error_message}")
        body_parts.append("")

    if errors:
        body_parts.append("--- Errors ---")
        for r in errors:
            body_parts.append(f"  ✗ {r.company_name} ({r.company_url}) — {r.error_message}")
        body_parts.append("")

    body = "\n".join(body_parts)

    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = f"FormFillerouter Run Summary — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        msg["From"] = settings.contact.email
        msg["To"] = settings.behavior.summary_email

        # Use Gmail SMTP if configured (same pattern as email_monitor)
        gmail_email = settings.contact.email
        gmail_password = None  # would come from .env in production
        if gmail_password:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_email, gmail_password)
                server.send_message(msg)
            logger.info("Summary email sent to %s", settings.behavior.summary_email)
        else:
            logger.info("Summary email (not sent — no SMTP password configured):\n%s", body)
    except Exception as e:
        logger.error("Failed to send summary email: %s", e)
        logger.info("Summary would have been:\n%s", body)


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Seattle GiveCamp — Form Fillerouter (Sponsorship Form Agent)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyze forms but do not submit")
    parser.add_argument("--company", help="Process a single company by name (substring match)")
    parser.add_argument("--url", help="Process a single URL directly")
    parser.add_argument("--no-sheets", action="store_true",
                        help="Skip Google Sheets (tracking/dedup)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Load config ─────────────────────────────────────────────────────
    try:
        settings = load_settings()
    except FileNotFoundError as e:
        logger.fatal("Config error: %s", e)
        sys.exit(1)

    # ── Init components ─────────────────────────────────────────────────
    llm = LLMClient(settings)
    filler = FormFiller(settings, llm)
    db = init_db(settings.log_db_path)

    # ── Determine targets ───────────────────────────────────────────────
    sheets = None  # only used when reading from Google Sheets
    if args.url:
        targets = [("Direct URL", args.url)]
    elif args.company:
        sheets = GoogleSheetsClient(settings.google_sheet)
        if sheets.connect():
            all_targets = sheets.get_targets()
            targets = [(t.name, t.url) for t in all_targets if args.company.lower() in t.name.lower()]
            if not targets:
                logger.error("No company matching '%s' found in Forms tab.", args.company)
                sys.exit(1)
        else:
            logger.error("Cannot connect to Google Sheets and no --url provided.")
            sys.exit(1)
    else:
        sheets = GoogleSheetsClient(settings.google_sheet)
        if not args.no_sheets and sheets.connect():
            all_targets = sheets.get_targets()
            tracked_urls = sheets.get_tracked_urls()

            # Dedup
            targets = []
            skipped_count = 0
            for t in all_targets:
                if t.url in tracked_urls:
                    logger.info("Skipping (already tracked): %s (%s)", t.name, t.url)
                    skipped_count += 1
                else:
                    targets.append((t.name, t.url))

            logger.info("Targets: %d pending, %d skipped (already tracked)",
                         len(targets), skipped_count)
        else:
            logger.error("Cannot connect to Google Sheets and no targets specified.")
            logger.error("Use --url to process a single URL, or fix Google Sheets config.")
            sys.exit(1)

    if not targets:
        logger.info("No pending targets. All done!")
        return

    # ── Process each company ────────────────────────────────────────────
    results: list[FormResult] = []

    for i, (name, url) in enumerate(targets):
        logger.info("── [%d/%d] Processing: %s ──", i + 1, len(targets), name)

        if args.dry_run:
            logger.info("DRY RUN — would process: %s (%s)", name, url)
            results.append(FormResult(
                company_name=name, company_url=url,
                success=False, status="dry_run",
            ))
            continue

        result = filler.process_company(name, url)
        results.append(result)
        log_submission(db, result)

        # Record in Google Sheets if successful
        if result.status == "submitted" and not args.no_sheets and sheets is not None:
            try:
                sheets.record_submission(name, url)
            except Exception as e:
                logger.error("Failed to record submission in sheets: %s", e)

        # Summary after each company
        logger.info("Result for %s: %s", name, result.status)
        if result.error_message:
            logger.info("  → %s", result.error_message)

    # ── Final summary ───────────────────────────────────────────────────
    submitted = sum(1 for r in results if r.status == "submitted")
    skipped = sum(1 for r in results if r.status in ("skipped", "requires_w9", "no_form_found", "dry_run"))
    errors = sum(1 for r in results if r.status == "error")

    logger.info("=" * 60)
    logger.info("RUN COMPLETE — %d total: %d submitted, %d skipped, %d errors",
                 len(results), submitted, skipped, errors)
    logger.info("=" * 60)

    # Send summary email
    send_summary_email(settings, results)

    db.close()


if __name__ == "__main__":
    main()
