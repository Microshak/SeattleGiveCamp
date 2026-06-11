"""
Scheduler — runs the full email processing pipeline on an interval.

Uses APScheduler to trigger the poll → classify → route → respond pipeline
at the configured interval (default: 60 minutes).
"""

import json
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from email_monitor.auth import validate_gmail_credentials
from email_monitor.classifier import PhiClassifier
from email_monitor.config import settings
from email_monitor.db import close_db, get_connection
from email_monitor.kb import KnowledgeBaseManager
from email_monitor.poller import fetch_unread
from email_monitor.router import route
from email_monitor.sheets import delete_nonprofit_row_by_email

logger = logging.getLogger(__name__)


# ── Sponsorship dedup helper ───────────────────────────────────────────

def _handle_sponsorship_dedup(msg: dict):
    """
    If the incoming email subject matches the configured sponsorship
    outreach subject, remove the sender's email from the Nonprofits
    worksheet in the sponsorship Google Sheet.
    """
    expected_subject = settings.sponsor_email_subject
    if not expected_subject:
        return

    actual_subject = msg.get("subject", "")
    # Normalize: strip Re:/Fwd: prefixes and whitespace for comparison
    import re
    normalized = re.sub(r"^(Re|Fwd?|RE|FWD?)\s*:\s*", "", actual_subject).strip()

    if normalized.lower() != expected_subject.lower():
        return

    sender_email = msg.get("sender_email", "")
    if not sender_email:
        logger.warning("Sponsorship subject matched but no sender email found.")
        return

    logger.info(
        "Sponsorship email subject detected from %s — removing from Nonprofits sheet.",
        sender_email,
    )

    deleted = delete_nonprofit_row_by_email(
        sheet_url=settings.sponsor_sheet_url,
        sheet_name=settings.sponsor_sheet_name,
        service_account_file=settings.sponsor_service_account_file,
        email=sender_email,
    )

    if deleted:
        logger.info("Removed %s from Nonprofits sheet.", sender_email)
    else:
        logger.info(
            "Email %s not found in Nonprofits sheet (may have been removed already).",
            sender_email,
        )


class EmailPoller:
    """Orchestrates one cycle of the email processing pipeline."""

    def __init__(self):
        self.classifier = PhiClassifier()
        self.kb_manager = KnowledgeBaseManager()

    def run_once(self):
        """
        Execute one full poll cycle:
          auth → fetch → (classify → route → respond/escalate) per message
        """
        logger.info("=== Starting poll cycle ===")

        # 1. Auth
        try:
            validate_gmail_credentials()
        except Exception as exc:
            logger.error("Gmail auth failed: %s — skipping cycle", exc)
            return

        # 2. Fetch unread
        messages = fetch_unread(top=50)
        if not messages:
            logger.info("No unread messages found.")
            return

        logger.info("Fetched %d unread message(s)", len(messages))

        # 3. Process each message
        for msg in messages:
            try:
                self._process_message(msg)
            except Exception as exc:
                logger.exception(
                    "Error processing message %s: %s", msg.get("id", "?"), exc
                )
                # Continue with the next message — don't crash the cycle

        logger.info("=== Poll cycle complete ===")

    def _process_message(self, msg: dict):
        """Classify, route, and respond to a single email."""
        conv_id = msg.get("conversationId", msg["id"])
        logger.info(
            "Processing message %s (conv=%s, from=%s)",
            msg["id"][:12],
            conv_id[:12],
            msg["sender_email"],
        )

        # 3a. Classify
        classification = self.classifier.classify(msg["body_text"])
        logger.debug(
            "Classification: intent=%s confidence=%.2f",
            classification.get("intent", "?"),
            classification.get("confidence", 0.0),
        )

        # 3b. KB retrieval for non-dropout intents
        kb_hits = []
        intent = classification.get("intent", "")
        if intent not in ("volunteer_dropout", "unclear"):
            kb_query = classification.get("suggested_kb_query", "")
            if kb_query:
                kb_hits = self.kb_manager.search(kb_query, top_k=3)
                logger.debug("KB hits: %d", len(kb_hits))

        # 3c. Route
        result = route(msg, classification, kb_hits)

        # 3d. If the subject matches the sponsorship outreach email,
        #     remove the sender from the Nonprofits sheet (dedup).
        _handle_sponsorship_dedup(msg)

        # 3e. Send response if the router composed one
        if result.get("action") == "sent" and result.get("response"):
            from email_monitor.composer import compose_and_send

            compose_and_send(
                to_address=msg["sender_email"],
                subject=f"Re: {msg['subject']}",
                body_html=result["response"],
            )

        logger.info(
            "Done: msg=%s action=%s handler=%s",
            msg["id"][:12],
            result.get("action", "?"),
            result.get("handler", "?"),
        )


# ── Scheduler lifecycle ──────────────────────────────────────────────────

_scheduler: BackgroundScheduler | None = None


def start_scheduler():
    """Create and start the APScheduler background scheduler."""
    global _scheduler

    # Ensure DB is initialized
    get_connection()

    # Init KB / Milvus
    kb = KnowledgeBaseManager()
    kb.init_milvus()
    if kb.check_reindex_needed():
        kb.index_documents()
    else:
        logger.info("KB is up to date; skipping index.")

    poller = EmailPoller()

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        poller.run_once,
        trigger="interval",
        minutes=settings.poll_interval_minutes,
        id="email_poll",
        replace_existing=True,
    )

    # Run once immediately on startup
    _scheduler.add_job(
        poller.run_once,
        trigger="date",
        id="email_poll_initial",
        run_date=None,  # as soon as possible
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — polling every %d minutes",
        settings.poll_interval_minutes,
    )


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None:
        logger.info("Stopping scheduler…")
        _scheduler.shutdown(wait=False)
        _scheduler = None
