"""
Gmail authentication helpers for the Seattle GiveCamp email monitor.

This module handles IMAP login for fetching unread Gmail messages and SMTP
login for sending email replies via Gmail App Password authentication.
"""

import imaplib
import smtplib

from email_monitor.config import settings


def _ensure_gmail_config() -> None:
    if not settings.gmail_email or not settings.gmail_app_password:
        raise RuntimeError(
            "GMAIL_EMAIL and GMAIL_APP_PASSWORD must be set in .env "
            "for Gmail IMAP/SMTP access."
        )


def imap_connect() -> imaplib.IMAP4_SSL:
    """Return a connected and authenticated Gmail IMAP session."""
    _ensure_gmail_config()
    conn = imaplib.IMAP4_SSL(settings.gmail_imap_host, settings.gmail_imap_port)
    conn.login(settings.gmail_email, settings.gmail_app_password)
    return conn


def smtp_connect() -> smtplib.SMTP_SSL:
    """Return a connected and authenticated Gmail SMTP session."""
    _ensure_gmail_config()
    smtp = smtplib.SMTP_SSL(settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=30)
    smtp.login(settings.gmail_email, settings.gmail_app_password)
    return smtp


def validate_gmail_credentials() -> None:
    """Validate Gmail credentials by opening and closing an IMAP session."""
    conn = imap_connect()
    try:
        conn.noop()
    finally:
        try:
            conn.logout()
        except Exception:
            pass

