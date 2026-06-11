#!/usr/bin/env python3
"""
Seattle GiveCamp Email Monitoring & Response System — Entry Point.

Starts the scheduler (APScheduler) and Telegram bot, then waits for shutdown.

Usage:
    cd mail_service
    python -m email_monitor.main
"""

import logging
import signal
import sys
from threading import Event

from email_monitor.config import settings
from email_monitor.kb import KnowledgeBaseManager
from email_monitor.scheduler import start_scheduler, stop_scheduler
from email_monitor.telegram_bot import start_polling, stop as stop_telegram

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Shutdown event for graceful termination
_shutdown_event = Event()


def _handle_signal(signum, frame):
    if _shutdown_event.is_set():
        logger.warning("Already shutting down — forcing exit.")
        sys.exit(1)
    logger.info("Received signal %d — shutting down…", signum)
    _shutdown_event.set()


def main():
    print("=" * 60)
    print("  Seattle GiveCamp Email Monitor")
    print(f"  Poll interval: {settings.poll_interval_minutes} min")
    print(f"  Confidence thresholds: auto ≥{settings.confidence_auto}, review ≥{settings.confidence_review}")
    print("=" * 60)

    # Remind about Gmail credentials
    print()
    print("  NOTE: This app connects to Gmail via IMAP/SMTP.")
    print("  Set GMAIL_EMAIL and GMAIL_APP_PASSWORD in .env before running.")

    # Register signal handlers
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Start Telegram bot (runs in its own background thread)
    if settings.telegram_bot_token and settings.telegram_chat_id:
        logger.info("Telegram bot configured — starting")
        start_polling()
    else:
        logger.warning(
            "Telegram bot not configured. Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env for escalation alerts."
        )

    # Start the scheduler (runs poll cycle immediately, then on interval)
    start_scheduler()

    # Wait for shutdown signal
    logger.info("System running. Press Ctrl+C to stop.")
    try:
        _shutdown_event.wait()
    except KeyboardInterrupt:
        pass

    # Graceful shutdown
    logger.info("Shutting down…")
    stop_scheduler()
    stop_telegram()

    from email_monitor.db import close_db
    close_db()

    # Close Milvus / KB connection
    try:
        kb = KnowledgeBaseManager()
        kb.close()
    except Exception:
        pass

    logger.info("Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    main()
