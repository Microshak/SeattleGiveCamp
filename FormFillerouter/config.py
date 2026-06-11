"""
Configuration loader — reads YAML configs + .env and exposes a unified Settings object.

Profiles:
  - givecamp_profile.yaml  → org identity, contact, tiers, behavior
  - targets.yaml           → Google Sheet connection, tab layouts
  - prompts.yaml           → LLM system prompts
  - .env                   → LLM_BASE_URL, LLM_MODEL, PLAYWRIGHT_HEADLESS, etc.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── Project root ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


def _load_yaml(filename: str) -> dict:
    path = PROJECT_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"Required config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, str(default)).lower()
    return val in ("true", "1", "yes")


@dataclass
class OrgProfile:
    legal_name: str
    type: str
    ein: str
    website: str
    year_founded: int
    state_of_incorporation: str


@dataclass
class ContactInfo:
    name: str
    title: str
    email: str
    phone: str
    street: str
    city: str
    state: str
    zip: str


@dataclass
class EventInfo:
    name: str
    location: str
    date_2026: str
    nonprofits_served_per_year: int
    volunteers_per_year: int
    years_running: int


@dataclass
class MissionTexts:
    one_sentence: str
    paragraph: str
    impact_statement: str


@dataclass
class SponsorValue:
    short: str
    long: str


@dataclass
class SponsorshipTier:
    name: str
    amount: str
    benefits: str


@dataclass
class Behavior:
    default_tier: str
    attach_sponsorship_deck: bool
    how_did_you_hear: str
    skip_on_w9_required: bool
    boilerplate_extra: str
    summary_email: str


@dataclass
class GoogleSheetConfig:
    url: str
    service_account_file: str
    forms_tab: str
    tracking_tab: str
    forms_company_col: int
    forms_url_col: int
    forms_notes_col: int
    tracking_company_col: int
    tracking_agent_col: int
    tracking_url_col: int
    agent_name: str
    dedup_on_column: int


@dataclass
class Prompts:
    system: str
    analyze_form: str
    validate_before_submit: str
    find_sponsorship_page: str


@dataclass
class Settings:
    org: OrgProfile
    contact: ContactInfo
    event: EventInfo
    mission: MissionTexts
    sponsor_value: SponsorValue
    tiers: list[SponsorshipTier]
    default_tier: str
    social: dict
    sponsorship_deck_url: str
    behavior: Behavior
    google_sheet: GoogleSheetConfig
    prompts: Prompts

    # ── From .env ───────────────────────────────────────────────────────
    llm_base_url: str = field(default_factory=lambda: _env_str("LLM_BASE_URL", "http://localhost:8080/v1"))
    llm_model: str = field(default_factory=lambda: _env_str("LLM_MODEL", "qwen3.5-35b-a3b"))
    playwright_headless: bool = field(default_factory=lambda: _env_bool("PLAYWRIGHT_HEADLESS", True))
    log_db_path: str = field(default_factory=lambda: _env_str("LOG_DB_PATH", "./logs/submissions.db"))
    screenshot_dir: str = field(default_factory=lambda: _env_str("SCREENSHOT_DIR", "./screenshots"))


def load_settings() -> Settings:
    """Load all YAML configs and return a unified Settings object."""
    profile = _load_yaml("givecamp_profile.yaml")
    targets = _load_yaml("targets.yaml")
    prompts = _load_yaml("prompts.yaml")

    # ── Org ─────────────────────────────────────────────────────────────
    org_data = profile["org"]
    org = OrgProfile(
        legal_name=org_data["legal_name"],
        type=org_data["type"],
        ein=org_data["ein"],
        website=org_data["website"],
        year_founded=org_data["year_founded"],
        state_of_incorporation=org_data["state_of_incorporation"],
    )

    # ── Contact ─────────────────────────────────────────────────────────
    contact_data = profile["contact"]
    addr = contact_data["mailing_address"]
    contact = ContactInfo(
        name=contact_data["name"],
        title=contact_data["title"],
        email=contact_data["email"],
        phone=contact_data["phone"],
        street=addr["street"],
        city=addr["city"],
        state=addr["state"],
        zip=addr["zip"],
    )

    # ── Event ───────────────────────────────────────────────────────────
    event_data = profile["event"]
    event = EventInfo(
        name=event_data["name"],
        location=event_data["location"],
        date_2026=event_data["date_2026"],
        nonprofits_served_per_year=event_data["nonprofits_served_per_year"],
        volunteers_per_year=event_data["volunteers_per_year"],
        years_running=event_data["years_running"],
    )

    # ── Mission ─────────────────────────────────────────────────────────
    mission_data = profile["mission"]
    mission = MissionTexts(
        one_sentence=mission_data["one_sentence"],
        paragraph=mission_data["paragraph"],
        impact_statement=mission_data["impact_statement"],
    )

    # ── Sponsor Value ───────────────────────────────────────────────────
    sv = profile["sponsor_value"]
    sponsor_value = SponsorValue(short=sv["short"], long=sv["long"])

    # ── Tiers ───────────────────────────────────────────────────────────
    tiers = [
        SponsorshipTier(name=t["name"], amount=t["amount"], benefits=t["benefits"])
        for t in profile["sponsorship_tiers"]
    ]

    # ── Behavior ────────────────────────────────────────────────────────
    behavior_data = profile["behavior"]
    behavior = Behavior(
        default_tier=behavior_data["default_tier"],
        attach_sponsorship_deck=behavior_data["attach_sponsorship_deck"],
        how_did_you_hear=behavior_data["how_did_you_hear"],
        skip_on_w9_required=behavior_data["skip_on_w9_required"],
        boilerplate_extra=behavior_data["boilerplate_extra"],
        summary_email=behavior_data["summary_email"],
    )

    # ── Google Sheet ────────────────────────────────────────────────────
    gs = targets["google_sheet"]
    ft = targets["forms_tab_layout"]
    tt = targets["tracking_tab_layout"]
    tk = targets["tracking"]
    google_sheet = GoogleSheetConfig(
        url=gs["url"],
        service_account_file=str(PROJECT_ROOT / gs["service_account_file"]),
        forms_tab=gs["forms_tab"],
        tracking_tab=gs["tracking_tab"],
        forms_company_col=ft["company_col"],
        forms_url_col=ft["url_col"],
        forms_notes_col=ft["notes_col"],
        tracking_company_col=tt["company_col"],
        tracking_agent_col=tt["agent_col"],
        tracking_url_col=tt["url_col"],
        agent_name=tk["agent_name"],
        dedup_on_column=tk["dedup_on_column"],
    )

    # ── Prompts ─────────────────────────────────────────────────────────
    prompts_obj = Prompts(
        system=prompts["system"],
        analyze_form=prompts["analyze_form"],
        validate_before_submit=prompts["validate_before_submit"],
        find_sponsorship_page=prompts["find_sponsorship_page"],
    )

    return Settings(
        org=org,
        contact=contact,
        event=event,
        mission=mission,
        sponsor_value=sponsor_value,
        tiers=tiers,
        default_tier=behavior.default_tier,
        social=profile["social"],
        sponsorship_deck_url=profile["sponsorship_deck_url"],
        behavior=behavior,
        google_sheet=google_sheet,
        prompts=prompts_obj,
    )


def build_profile_text(settings: Settings) -> str:
    """Build a compact text profile for injection into LLM prompts."""
    c = settings.contact
    o = settings.org
    e = settings.event
    m = settings.mission

    tier_lines = "\n".join(
        f"    - {t.name}: {t.amount} — {t.benefits}"
        for t in settings.tiers
    )

    return f"""
Organization: {o.legal_name} ({o.type})
EIN: {o.ein}
Website: {o.website}
Founded: {o.year_founded} in {o.state_of_incorporation}

Contact Person: {c.name}, {c.title}
Email: {c.email}
Phone: {c.phone}
Mailing Address: {c.street}, {c.city}, {c.state} {c.zip}

Event: {e.name}
Location: {e.location}
Next Event Date: {e.date_2026}
Years Running: {e.years_running}
Nonprofits Served/Year: {e.nonprofits_served_per_year}
Volunteers/Year: {e.volunteers_per_year}

Mission: {m.one_sentence}
{m.paragraph}

Impact: {m.impact_statement}

Sponsorship Tiers:
{tier_lines}

Default tier to request: {settings.default_tier}

Value to Sponsor (short): {settings.sponsor_value.short}

Social: LinkedIn={settings.social.get('linkedin','')}, YouTube={settings.social.get('youtube','')}
""".strip()
