"""
Intent router — branches on classification results and dispatches to handlers.

Implements the confidence routing matrix from PRD §4.3:
  ≥0.85  → auto-handle
  0.70–0.84 → handle but flag for audit
  <0.70  → escalate to Telegram immediately
"""

import csv
import json
import logging
import os
import tempfile
from typing import Optional

from email_monitor.classifier import PhiClassifier
from email_monitor.composer import compose_and_send
from email_monitor.config import settings
from email_monitor.db import (
    append_intent,
    append_message,
    get_or_create_thread,
    log_response,
    update_thread,
)
from email_monitor.kb import SIMILARITY_THRESHOLD
from email_monitor.templates import ResponseTemplates

logger = logging.getLogger(__name__)

templates = ResponseTemplates()
classifier = PhiClassifier()


def route(
    email_data: dict,
    classification: dict,
    kb_hits: Optional[list[dict]] = None,
) -> dict:
    """
    Route an email based on its classification and return the action taken.

    Args:
        email_data: dict with id, conversationId, subject, sender_email, sender_name, body_text
        classification: dict from PhiClassifier.classify()
        kb_hits: optional list of Milvus search results

    Returns:
        dict with action, handler, response, escalated keys
    """
    thread_id = email_data.get("conversationId", email_data["id"])
    confidence = classification.get("confidence", 0.0)
    intent = classification.get("intent", "unclear")

    # ── Resolve / create thread ────────────────────────────────────────
    thread = get_or_create_thread(
        thread_id=thread_id,
        contact_email=email_data["sender_email"],
        contact_name=email_data["sender_name"],
    )
    append_message(thread_id, "user", email_data["body_text"])
    append_intent(thread_id, classification)

    # ── Confidence routing ─────────────────────────────────────────────
    if confidence < settings.confidence_review:
        return _escalate(thread_id, email_data, classification, kb_hits, reason="low_confidence")

    # ── Intent dispatch ────────────────────────────────────────────────
    handler_map = {
        "volunteer_dropout": _handle_volunteer_dropout,
        "sponsor_inquiry": _handle_sponsor_inquiry,
        "event_question": _handle_event_question,
        "media_inquiry": _handle_media_inquiry,
        "general": _handle_general,
        "unclear": _handle_general,
    }

    handler = handler_map.get(intent, _handle_general)
    result = handler(thread_id, email_data, classification, kb_hits or [])

    # Mark for audit if confidence is in the review band
    if confidence < settings.confidence_auto:
        result["flagged_for_audit"] = True

    return result


# ── Individual handlers ──────────────────────────────────────────────────


def _handle_volunteer_dropout(
    thread_id: str, email: dict, classification: dict, kb_hits: list
) -> dict:
    """
    Match sender email against volunteer CSV.
    If found: remove row, send confirmation.
    If not found: send "not found" template, log for review.
    """
    sender_email = email["sender_email"].lower()
    csv_path = settings.volunteer_csv

    if not os.path.isfile(csv_path):
        logger.warning("Volunteer CSV not found at %s", csv_path)
        body_html = templates.volunteer_not_found(sender_email)
        _log_and_update(thread_id, email, classification, [], body_html, "template")
        return _action("sent", "template", body_html)

    # Read CSV, find and remove the matching row
    rows = []
    found = False
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get("email", "").strip().lower() == sender_email:
                found = True
                logger.info("Removed volunteer %s from CSV", sender_email)
                continue  # skip this row
            rows.append(row)

    if found:
        # Write updated CSV atomically
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(csv_path), suffix=".csv")
        try:
            with os.fdopen(fd, "w", newline="") as tmp:
                writer = csv.DictWriter(tmp, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(tmp_path, csv_path)
        except Exception:
            os.unlink(tmp_path)
            raise

        body_html = templates.volunteer_dropout_confirmation(email["sender_name"])
        _log_and_update(thread_id, email, classification, [], body_html, "template")
        return _action("sent", "template", body_html)
    else:
        body_html = templates.volunteer_not_found(sender_email)
        _log_and_update(thread_id, email, classification, [], body_html, "template")
        return _action("sent", "template", body_html, escalated=True)


def _handle_sponsor_inquiry(
    thread_id: str, email: dict, classification: dict, kb_hits: list
) -> dict:
    """Use KB context + Phi draft to compose a sponsorship reply."""
    kb_context = _format_kb_context(kb_hits)
    if not kb_context:
        return _escalate(thread_id, email, classification, kb_hits, reason="no_kb_hits")

    draft = classifier.draft_reply(kb_context, email["body_text"], email["sender_name"])
    body_html = _wrap_draft(draft, is_sponsor=True)
    _log_and_update(thread_id, email, classification, kb_hits, body_html, "phi_draft")
    return _action("sent", "phi_draft", body_html)


def _handle_event_question(
    thread_id: str, email: dict, classification: dict, kb_hits: list
) -> dict:
    """KB lookup → if hit ≥ threshold draft reply; else escalate."""
    kb_context = _format_kb_context(kb_hits, min_score=SIMILARITY_THRESHOLD)
    if not kb_context:
        return _escalate(thread_id, email, classification, kb_hits, reason="no_kb_hits")

    draft = classifier.draft_reply(kb_context, email["body_text"], email["sender_name"])
    body_html = _wrap_draft(draft)
    _log_and_update(thread_id, email, classification, kb_hits, body_html, "phi_draft")
    return _action("sent", "phi_draft", body_html)


def _handle_media_inquiry(
    thread_id: str, email: dict, classification: dict, kb_hits: list
) -> dict:
    """Media inquiries are always escalated (sensitive)."""
    return _escalate(thread_id, email, classification, kb_hits, reason="media_inquiry")


def _handle_general(
    thread_id: str, email: dict, classification: dict, kb_hits: list
) -> dict:
    """Attempt KB retrieval; if hit, draft with Phi; otherwise escalate."""
    kb_context = _format_kb_context(kb_hits, min_score=SIMILARITY_THRESHOLD)
    if not kb_context:
        return _escalate(thread_id, email, classification, kb_hits, reason="no_kb_hits")

    draft = classifier.draft_reply(kb_context, email["body_text"], email["sender_name"])
    body_html = _wrap_draft(draft)
    _log_and_update(thread_id, email, classification, kb_hits, body_html, "phi_draft")
    return _action("sent", "phi_draft", body_html)


# ── Escalation ───────────────────────────────────────────────────────────


def _escalate(
    thread_id: str,
    email: dict,
    classification: dict,
    kb_hits: Optional[list],
    reason: str = "",
) -> dict:
    """Mark thread as escalated and log the response (no email sent)."""
    update_thread(thread_id, status="escalated")
    _log_and_update(thread_id, email, classification, kb_hits or [], "", "human_relay", escalated=True)

    from email_monitor.telegram_bot import send_escalation
    import asyncio

    # Use a dedicated thread with its own persistent event loop
    # to avoid "Event loop is closed" on subsequent escalations
    def _run_escalation():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(send_escalation(email, classification, kb_hits or []))
        finally:
            loop.close()

    import threading
    t = threading.Thread(target=_run_escalation, daemon=True)
    t.start()

    return _action("escalated", "human_relay", None)


# ── Helpers ──────────────────────────────────────────────────────────────


def _action(action: str, handler: str, response: Optional[str], escalated: bool = False) -> dict:
    return {
        "action": action,
        "handler": handler,
        "response": response,
        "escalated": escalated,
    }


def _log_and_update(
    thread_id: str,
    email: dict,
    classification: dict,
    kb_hits: list,
    body_html: str,
    handler: str,
    escalated: bool = False,
):
    log_response(
        thread_id=thread_id,
        message_id=email["id"],
        classification_json=json.dumps(classification),
        kb_hits=kb_hits,
        response_sent=body_html,
        handler=handler,
        escalated=escalated,
    )
    new_status = "escalated" if escalated else "resolved"
    update_thread(thread_id, status=new_status)
    append_message(thread_id, "assistant", body_html or "(escalated)")


def _format_kb_context(kb_hits: list, min_score: float = 0.0) -> str:
    """Format KB hits into a text block for prompt injection, filtering by min_score."""
    parts = []
    for hit in kb_hits:
        score = hit.get("score", 0.0)
        if score < min_score:
            continue
        title = hit.get("title", "Untitled")
        body = hit.get("body", "")
        parts.append(f"--- {title} (relevance: {score:.2f}) ---\n{body}")
    return "\n\n".join(parts)


def _wrap_draft(draft: str, is_sponsor: bool = False) -> str:
    """Wrap a Phi draft with standard footer and optional 501(c)(3) footer."""
    html = draft.replace("\n", "<br>\n")
    html += f"<br>\n{ResponseTemplates.standard_footer()}"
    if is_sponsor:
        html += f"<br>\n{ResponseTemplates.sponsor_501c3_footer()}"
    return html
