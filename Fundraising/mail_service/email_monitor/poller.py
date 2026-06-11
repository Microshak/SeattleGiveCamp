"""
Gmail email poller — fetches unread messages from Gmail and sends replies.

Uses Gmail IMAP for inbox polling and SMTP for outgoing replies.
Already-processed message IDs are tracked in SQLite's response_log
table to avoid re-processing messages that have already been handled.
"""

import imaplib
import logging
import re
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Optional

from email_monitor.auth import imap_connect, smtp_connect
from email_monitor.config import settings

logger = logging.getLogger(__name__)


def get_processed_ids() -> set[str]:
    """Return the set of message IDs already processed."""
    from email_monitor.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT message_id FROM response_log"
    ).fetchall()
    return {row["message_id"] for row in rows}


def fetch_unread(top: int = 50) -> list[dict]:
    """Fetch unread Gmail messages from the configured inbox."""
    already_processed = get_processed_ids()

    try:
        conn = imap_connect()
    except Exception as exc:
        logger.error("IMAP connection failed: %s", exc)
        return []

    try:
        conn.select("INBOX")
        typ, data = conn.uid("search", None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            return []

        uids = data[0].split()
        if not uids:
            return []

        uids = uids[-top:]
        messages = []

        for uid in reversed(uids):
            uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
            typ, fetch_data = conn.uid("fetch", uid_str, "(RFC822)")
            if typ != "OK" or not fetch_data or not fetch_data[0]:
                continue

            raw = fetch_data[0][1]
            if not raw:
                continue

            msg = message_from_bytes(raw)
            if uid_str in already_processed:
                logger.debug("Skipping already-processed message %s", uid_str)
                continue

            sender_name, sender_email = parseaddr(msg.get("From", ""))
            messages.append(
                {
                    "id": uid_str,
                    "conversationId": msg.get("In-Reply-To")
                    or msg.get("References")
                    or msg.get("Message-ID")
                    or uid_str,
                    "subject": _decode_header(msg.get("Subject", "")),
                    "sender_email": sender_email,
                    "sender_name": sender_name,
                    "body_text": _extract_text(msg),
                    "received": msg.get("Date", ""),
                }
            )

        return messages
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def send_email(
    to_address: str,
    subject: str,
    body_html: str,
) -> bool:
    """Send an email through Gmail SMTP using the configured account."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.gmail_email
    msg["To"] = to_address
    msg.set_content("This email requires an HTML-compatible email client.")
    msg.add_alternative(body_html, subtype="html")

    try:
        with smtp_connect() as smtp:
            smtp.send_message(msg)
        logger.info("Email sent to %s — subject: %s", to_address, subject)
        return True
    except Exception as exc:
        logger.error("SMTP send failed: %s", exc)
        return False


def _decode_header(value: Optional[str]) -> str:
    if not value:
        return ""

    parts = decode_header(value)
    decoded_parts = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            decoded_parts.append(
                part.decode(encoding or "utf-8", errors="replace")
            )
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _extract_text(msg) -> str:
    """Extract plain text from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if content_type == "text/plain" and disposition != "attachment":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace",
                    ).strip()
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if content_type == "text/html" and disposition != "attachment":
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace",
                    )
                    return _strip_html(html)
        return ""

    payload = msg.get_payload(decode=True)
    if not payload:
        return ""

    return payload.decode(
        msg.get_content_charset() or "utf-8",
        errors="replace",
    ).strip()


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text
