"""
Configuration loader — reads all settings from environment / .env file.

Follows the 12-factor app pattern. All configurable values live in one place
so the rest of the system can import Settings without knowing where values
come from.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ── Project root is the repo root (parent of mail_service/) ──────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_dotenv_path = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_dotenv_path)

# Ensure HuggingFace cache is writable (needed for sentence-transformers)
_hf_default = str(Path.home() / ".cache" / "huggingface")
os.environ["HF_HOME"] = _hf_default
Path(_hf_default).mkdir(parents=True, exist_ok=True)


def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # ── Microsoft Graph / MSAL ───────────────────────────────────────────
    # (legacy Outlook settings preserved for backward reference)
    client_id: str = field(default_factory=lambda: _str("Application_id"))
    tenant_id: str = field(default_factory=lambda: _str("Tenant_id"))
    user_email: str = field(default_factory=lambda: _str("email_address"))
    mail_scopes: list[str] = field(
        default_factory=lambda: ["Mail.Send", "Mail.Read"]
    )

    # ── Gmail SMTP/IMAP ─────────────────────────────────────────────────
    gmail_email: str = field(default_factory=lambda: _str("GMAIL_EMAIL"))
    gmail_app_password: str = field(
        default_factory=lambda: _str("GMAIL_APP_PASSWORD")
    )
    gmail_imap_host: str = field(
        default_factory=lambda: _str("GMAIL_IMAP_HOST", "imap.gmail.com")
    )
    gmail_imap_port: int = field(default_factory=lambda: _int("GMAIL_IMAP_PORT", 993))
    gmail_smtp_host: str = field(
        default_factory=lambda: _str("GMAIL_SMTP_HOST", "smtp.gmail.com")
    )
    gmail_smtp_port: int = field(default_factory=lambda: _int("GMAIL_SMTP_PORT", 465))

    # ── llama.cpp server (OpenAI-compatible API) ────────────────────────
    # Shares the same server as FormFillerouter/llm.sh (port 8080).
    # Set LLM_BASE_URL / LLM_MODEL in .env to override.
    llm_base_url: str = field(
        default_factory=lambda: _str("LLM_BASE_URL", "http://localhost:8080/v1")
    )
    llm_model: str = field(default_factory=lambda: _str("LLM_MODEL", "qwen3.5-35b-a3b"))

    # ── Telegram ─────────────────────────────────────────────────────────
    telegram_bot_token: str = field(
        default_factory=lambda: _str("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: _str("TELEGRAM_CHAT_ID", "")
    )

    # ── Polling ──────────────────────────────────────────────────────────
    poll_interval_minutes: int = field(
        default_factory=lambda: _int("POLL_INTERVAL_MINUTES", 60)
    )

    # ── Confidence thresholds (PRD §4.3) ─────────────────────────────────
    confidence_auto: float = field(
        default_factory=lambda: _float("CONFIDENCE_THRESHOLD_AUTO", 0.85)
    )
    confidence_review: float = field(
        default_factory=lambda: _float("CONFIDENCE_THRESHOLD_REVIEW", 0.70)
    )

    # ── Milvus (embedded) ────────────────────────────────────────────────
    milvus_db_path: str = field(
        default_factory=lambda: _str(
            "MILVUS_DB_PATH",
            str(_PROJECT_ROOT / "mail_service" / "email_monitor" / "milvus_lite.db"),
        )
    )

    # ── Knowledge Base ───────────────────────────────────────────────────
    kb_dir: str = field(
        default_factory=lambda: _str("KB_DIR", str(_PROJECT_ROOT / "kb"))
    )

    # ── Volunteer CSV ────────────────────────────────────────────────────
    volunteer_csv: str = field(
        default_factory=lambda: _str(
            "VOLUNTEER_CSV",
            str(_PROJECT_ROOT / "mail_service" / "data" / "volunteers.csv"),
        )
    )

    # ── Paths ────────────────────────────────────────────────────────────
    cache_file: str = field(
        default_factory=lambda: _str(
            "TOKEN_CACHE_FILE",
            str(_PROJECT_ROOT / "mail_service" / "token_cache.bin"),
        )
    )
    db_path: str = field(
        default_factory=lambda: _str(
            "DB_PATH",
            str(_PROJECT_ROOT / "mail_service" / "email_monitor" / "thread_store.db"),
        )
    )

    # ── Shadow mode (PRD §9) ────────────────────────────────────────────
    # When True, emails are logged but NOT actually sent.
    # Set SAVE_OUTPUTS_ONLY=1 in .env to enable pre-launch validation.
    save_outputs_only: bool = field(
        default_factory=lambda: _str("SAVE_OUTPUTS_ONLY", "").lower() in ("1", "true", "yes")
    )

    # ── Sponsorship Google Sheet (for dedup when sponsorship email is received) ─
    sponsor_sheet_url: str = field(
        default_factory=lambda: _str("SPONSOR_SHEET_URL", "")
    )
    sponsor_sheet_name: str = field(
        default_factory=lambda: _str("SPONSOR_SHEET_NAME", "Nonprofits")
    )
    sponsor_service_account_file: str = field(
        default_factory=lambda: _str(
            "SPONSOR_SERVICE_ACCOUNT_FILE",
            str(_PROJECT_ROOT / "GMailer" / "seattlegivecamp-1373-0bf9a18afc34.json"),
        )
    )
    sponsor_email_subject: str = field(
        default_factory=lambda: _str(
            "SPONSOR_EMAIL_SUBJECT",
            "Support Seattle GiveCamp \u2013 October 17th Weekend",
        )
    )


# Single global instance so all modules share the same values.
settings = Settings()
