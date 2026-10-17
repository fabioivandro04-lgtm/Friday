"""Constrói o hub de integrações a partir das contas já ligadas."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from friday.config import IntegrationsConfig
from friday.integrations.auth import (
    GoogleTokenSource,
    MicrosoftTokenSource,
    _load_google,
    microsoft_app,
)
from friday.integrations.gmail import Gmail
from friday.integrations.google_calendar import GoogleCalendar
from friday.integrations.hub import IntegrationHub
from friday.integrations.microsoft import Outlook

GOOGLE_TOKEN = "google_token.json"
GOOGLE_CLIENT_SECRET = "client_secret.json"
MICROSOFT_CACHE = "microsoft_cache.json"


def build_hub(cfg: IntegrationsConfig, google_loader=_load_google, microsoft_factory=microsoft_app):
    tz = ZoneInfo(cfg.timezone)
    secrets = Path(cfg.secrets_dir)
    calendars, mailboxes = [], []
    if (secrets / GOOGLE_TOKEN).exists():
        token = GoogleTokenSource(secrets / GOOGLE_TOKEN, loader=google_loader)
        calendars.append(GoogleCalendar(token, tz))
        mailboxes.append(Gmail(token, tz))
    if cfg.microsoft_client_id and (secrets / MICROSOFT_CACHE).exists():
        app, cache = microsoft_factory(cfg.microsoft_client_id, secrets / MICROSOFT_CACHE)
        token = MicrosoftTokenSource(app, cache, secrets / MICROSOFT_CACHE)
        outlook = Outlook(token, tz)
        calendars.append(outlook)
        mailboxes.append(outlook)
    return IntegrationHub(calendars, mailboxes, default=cfg.default_provider)
