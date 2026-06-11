"""
Telegram escalation bot — alerts the event owner and relays replies as emails.

Uses python-telegram-bot's Application pattern.

The bot:
  1. Sends structured escalation alerts to the configured chat
  2. Listens for replies to escalation messages
  3. Relays the reply text as an email response via Gmail SMTP

To set up:
  1. Message @BotFather on Telegram to create a bot and get a token
  2. Put the token in .env as TELEGRAM_BOT_TOKEN
  3. Start the bot, message it once, then visit:
     https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
     to find your chat_id, and put it in .env as TELEGRAM_CHAT_ID
"""

import asyncio
import json
import logging
import threading
from typing import Optional

from telegram import Update
from telegram.ext import Application, MessageHandler, filters

from email_monitor.config import settings
from email_monitor.db import get_thread, log_response, update_thread
from email_monitor.poller import send_email

logger = logging.getLogger(__name__)

# ── In-memory mapping: Telegram message_id → thread_id ──────────────────
_escalation_map: dict[int, str] = {}


async def send_escalation(
    email_data: dict,
    classification: dict,
    kb_hits: Optional[list] = None,
):
    """Send a structured escalation alert to the configured Telegram chat."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning(
            "Telegram not configured — skipping escalation. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        )
        return

    # Import here to avoid circular import at module level
    from email_monitor.router import _format_kb_context

    intent = classification.get("intent", "unclear")
    confidence = classification.get("confidence", 0.0)
    sender = email_data.get("sender_name", "Unknown")
    sender_email = email_data.get("sender_email", "unknown@example.com")
    subject = email_data.get("subject", "(no subject)")
    body = email_data.get("body_text", "")
    body_truncated = body[:800] + ("…" if len(body) > 800 else "")

    kb_summary = _format_kb_context(kb_hits or [])[:300] if kb_hits else "None"

    message_text = (
        f"\U0001F6A8 *Escalation: {intent}*\n"
        f"*From:* {sender} <{sender_email}>\n"
        f"*Subject:* {subject}\n"
        f"*Confidence:* {confidence:.2f}\n\n"
        f"{body_truncated}\n\n"
        f"*KB matches:*\n{kb_summary}\n\n"
        f"Reply to this message to send your response as email."
    )

    application = _get_application()
    try:
        # We send synchronously using the bot directly
        result = await application.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=message_text,
            parse_mode="Markdown",
        )
        # Store mapping so reply_handler can find the thread
        _escalation_map[result.message_id] = email_data.get("conversationId", email_data["id"])
        logger.info(
            "Escalation sent to Telegram (message_id=%s)", result.message_id
        )
    except Exception as exc:
        logger.error("Failed to send Telegram escalation: %s", exc)


# ── Application singleton ───────────────────────────────────────────────

_application: Optional[Application] = None


def _get_application() -> Application:
    """Return or create the Telegram Application singleton."""
    global _application
    if _application is None:
        _application = Application.builder().token(settings.telegram_bot_token).build()
        _application.add_handler(
            MessageHandler(filters.REPLY & ~filters.COMMAND, _reply_handler)
        )
    return _application


async def _reply_handler(update: Update, context):
    """
    Handle a reply to an escalation message.

    The reply text is sent as an email response via Gmail SMTP.
    """
    if not update.message or not update.message.reply_to_message:
        return

    reply_to_id = update.message.reply_to_message.message_id
    thread_id = _escalation_map.get(reply_to_id)

    if not thread_id:
        await update.message.reply_text(
            "Could not find the original escalation for this reply."
        )
        logger.warning("No escalation mapping for message_id %s", reply_to_id)
        return

    reply_text = update.message.text or ""
    thread = get_thread(thread_id)
    if not thread:
        await update.message.reply_text("Thread not found in database.")
        return

    # Send the reply as email
    try:
        success = send_email(
            to_address=thread["contact_email"],
            subject=f"Re: Your Seattle GiveCamp Inquiry",
            body_html=reply_text.replace("\n", "<br>\n"),
        )

        if success:
            update_thread(thread_id, status="resolved")
            # Log the human relay
            log_response(
                thread_id=thread_id,
                message_id=f"tg-{reply_to_id}",
                classification_json="{}",
                kb_hits=[],
                response_sent=reply_text,
                handler="human_relay",
                escalated=False,
            )
            await update.message.reply_text(
                f"\u2713 Sent to {thread['contact_email']}"
            )
            logger.info(
                "Telegram relay: reply sent to %s", thread["contact_email"]
            )
        else:
            await update.message.reply_text(
                "\u2717 Failed to send email. Check logs."
            )

    except Exception as exc:
        logger.error("Telegram relay error: %s", exc)
        await update.message.reply_text(f"\u2717 Error: {exc}")


# ── Lifecycle ────────────────────────────────────────────────────────────

_stop_event = threading.Event()


async def _run_bot(app: Application):
    """Run the bot with its own event loop — no signal handler registration."""
    await app.initialize()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Telegram bot polling started.")

    # Keep running until told to stop
    while not _stop_event.is_set():
        await asyncio.sleep(0.5)

    logger.info("Telegram bot stopping…")
    await app.updater.stop()
    await app.shutdown()
    logger.info("Telegram bot stopped.")


def start_polling():
    """Start the Telegram bot in a background thread with its own event loop."""
    if not settings.telegram_bot_token:
        logger.info("Telegram bot token not configured — skipping bot start.")
        return

    app = _get_application()
    logger.info("Starting Telegram bot polling…")

    def _run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_bot(app))
        except Exception as exc:
            logger.error("Telegram bot error: %s", exc)
        finally:
            loop.close()

    _stop_event.clear()
    tg_thread = threading.Thread(target=_run_in_thread, daemon=True)
    tg_thread.start()


def stop():
    """Signal the Telegram bot to stop gracefully."""
    global _application
    if _application is not None:
        logger.info("Stopping Telegram bot…")
        _stop_event.set()
        _application = None
