from datetime import datetime

from friday.integrations.hub import IntegrationHub
from friday.integrations.panels import PanelFeeder

from .conftest import LISBON
from .test_hub import Cal, Mail, _ev, _mail

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=LISBON)


async def test_refresh_sends_agenda_and_inbox():
    sent = []

    async def emit(e):
        sent.append(e)

    hub = IntegrationHub(
        [Cal("google", [_ev("g", 10, "google")])], [Mail("google", [_mail("m1", 8, "google")])]
    )
    await PanelFeeder(hub, emit, now=lambda: NOW).refresh()
    agenda = next(e for e in sent if e["type"] == "agenda")["data"]
    inbox = next(e for e in sent if e["type"] == "inbox")["data"]
    assert agenda == {
        "connected": True,
        "items": [{"time": "10:00", "title": "ev g", "location": ""}],
    }
    assert inbox == {
        "connected": True,
        "items": [{"ref": "google:m1", "sender": "x", "subject": "s m1"}],
    }


async def test_refresh_without_accounts_reports_not_connected():
    sent = []

    async def emit(e):
        sent.append(e)

    await PanelFeeder(IntegrationHub([], []), emit, now=lambda: NOW).refresh()
    assert {"type": "agenda", "data": {"connected": False, "items": []}} in sent
    assert {"type": "inbox", "data": {"connected": False, "items": []}} in sent
