"""
Response composer — sends emails via Gmail SMTP using the poller's send function.

Bridges between the router's decisions and the SMTP send implementation.
"""

import logging

from email_monitor.config import settings
from email_monitor.poller import send_email as _send_via_smtp

logger = logging.getLogger(__name__)


def compose_and_send(
    to_address: str,
    subject: str,
    body_html: str,
) -> bool:
    """
    Send a composed email. Returns True on success.

    If the system is running in shadow mode (SAVE_OUTPUTS_ONLY),
    the email is logged but not actually sent — used for pre-launch validation.
    """
    if not subject:
        subject = "Seattle GiveCamp – Thank You for Reaching Out"

    if settings.save_outputs_only:
        logger.info(
            "[SHADOW MODE] Would send to %s — subject: %s — body length: %d chars",
            to_address, subject, len(body_html),
        )
        logger.debug("[SHADOW MODE] Body preview: %s", body_html[:500])
        return True

    success = _send_via_smtp(to_address, subject, body_html)

    if success:
        logger.info("Response sent to %s — subject: %s", to_address, subject)
    else:
        logger.error("Failed to send response to %s", to_address)

    return success
