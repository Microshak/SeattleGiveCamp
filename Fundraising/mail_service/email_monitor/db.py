"""
SQLite thread state store and audit log.

Two tables matching PRD §5.2:
  • threads        — per-conversation state, message history, status
  • response_log   — immutable audit trail for every processed message

WAL mode is enabled for concurrency safety.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from email_monitor.config import settings

# ── Schema ───────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS threads (
    thread_id       TEXT PRIMARY KEY,                     -- unique conversation identifier
    contact_email   TEXT NOT NULL,
    contact_name    TEXT DEFAULT '',
    intent_history  TEXT DEFAULT '[]',                    -- JSON array of prior intents
    message_history TEXT DEFAULT '[]',                    -- JSON array of {role, content, timestamp}
    status          TEXT NOT NULL DEFAULT 'open'           -- open | resolved | escalated | awaiting_human
        CHECK (status IN ('open', 'resolved', 'escalated', 'awaiting_human')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS response_log (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id           TEXT NOT NULL REFERENCES threads(thread_id),
    message_id          TEXT NOT NULL,                    -- IMAP message UID or unique message identifier
    classification_json TEXT NOT NULL,                    -- Full Phi output stored verbatim
    kb_hits             TEXT DEFAULT '[]',                -- JSON array of Milvus results
    response_sent       TEXT DEFAULT '',                  -- Final email body sent
    handler             TEXT NOT NULL DEFAULT ''           -- template | phi_draft | human_relay
        CHECK (handler IN ('template', 'phi_draft', 'human_relay', '')),
    escalated           INTEGER NOT NULL DEFAULT 0,
    sent_at             TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_response_log_thread
    ON response_log(thread_id);
"""


# ── Connection management ───────────────────────────────────────────────

_connection: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    """Return a singleton database connection (lazy init)."""
    global _connection
    if _connection is None:
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(settings.db_path, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.executescript(_SCHEMA_SQL)
        _connection.commit()
    return _connection


def close_db():
    """Close the database connection (call on shutdown)."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


# ── Thread operations ────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_thread(thread_id: str) -> Optional[dict]:
    """Return the thread row, or None if it doesn't exist."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def create_thread(
    thread_id: str, contact_email: str, contact_name: str = ""
) -> dict:
    """Create a new thread record and return it."""
    conn = get_connection()
    now = _now()
    conn.execute(
        """INSERT INTO threads (thread_id, contact_email, contact_name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (thread_id, contact_email, contact_name, now, now),
    )
    conn.commit()
    return get_thread(thread_id)


def get_or_create_thread(
    thread_id: str, contact_email: str, contact_name: str = ""
) -> dict:
    """Return existing thread or create a new one."""
    thread = get_thread(thread_id)
    if thread is not None:
        return thread
    return create_thread(thread_id, contact_email, contact_name)


def update_thread(thread_id: str, **fields) -> Optional[dict]:
    """
    Update arbitrary columns on a thread row.

    Fields like intent_history / message_history should be JSON strings.
    updated_at is always set to now.
    """
    if not fields:
        return get_thread(thread_id)

    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [thread_id]

    conn = get_connection()
    conn.execute(
        f"UPDATE threads SET {set_clause} WHERE thread_id = ?", values
    )
    conn.commit()
    return get_thread(thread_id)


def append_message(thread_id: str, role: str, content: str):
    """Append a {role, content, timestamp} entry to message_history."""
    thread = get_thread(thread_id)
    if thread is None:
        raise ValueError(f"Thread {thread_id} does not exist")

    history = json.loads(thread["message_history"])
    history.append(
        {"role": role, "content": content, "timestamp": _now()}
    )
    # Keep only the last 10 messages to bound context size
    history = history[-10:]
    update_thread(thread_id, message_history=json.dumps(history))


def append_intent(thread_id: str, classification: dict):
    """Append an intent classification to intent_history."""
    thread = get_thread(thread_id)
    if thread is None:
        raise ValueError(f"Thread {thread_id} does not exist")

    history = json.loads(thread["intent_history"])
    history.append(
        {
            "intent": classification.get("intent", "unclear"),
            "confidence": classification.get("confidence", 0.0),
            "timestamp": _now(),
        }
    )
    history = history[-20:]
    update_thread(thread_id, intent_history=json.dumps(history))


# ── Response log operations ──────────────────────────────────────────────


def log_response(
    thread_id: str,
    message_id: str,
    classification_json: str,
    kb_hits: list,
    response_sent: str,
    handler: str,
    escalated: bool = False,
) -> int:
    """Insert a response_log entry. Returns the log_id."""
    conn = get_connection()
    now = _now() if response_sent else None
    cur = conn.execute(
        """INSERT INTO response_log
               (thread_id, message_id, classification_json, kb_hits,
                response_sent, handler, escalated, sent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            thread_id,
            message_id,
            classification_json,
            json.dumps(kb_hits),
            response_sent,
            handler,
            1 if escalated else 0,
            now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_threads_by_status(status: str) -> list[dict]:
    """Return all threads with a given status."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM threads WHERE status = ? ORDER BY updated_at DESC",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]
