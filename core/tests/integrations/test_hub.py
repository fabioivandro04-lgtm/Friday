from datetime import date, datetime

import pytest

from friday.integrations.hub import IntegrationHub
from friday.integrations.models import CalendarEvent, MailSummary

from .conftest import LISBON


def _ev(id_, h, provider):
    return CalendarEvent(
        id_,
        f"ev {id_}",
        datetime(2026, 10, 17, h, tzinfo=LISBON),
        datetime(2026, 10, 17, h + 1, tzinfo=LISBON),
        provider,
    )


def _mail(id_, h, provider):
    return MailSummary(id_, "x", f"s {id_}", "", datetime(2026, 10, 17, h, tzinfo=LISBON), provider)


class Cal:
    def __init__(self, name, events, fail=False):
        self.name, self.events, self.fail, self.created = name, events, fail, []

    async def list_events(self, day):
        if self.fail:
            raise RuntimeError("down")
        return self.events

    async def create_event(self, title, start, end, attendees):
        self.created.append(title)
        return _ev("new", start.hour, self.name)


class Mail:
    def __init__(self, name, mails):
        self.name, self.mails, self.sent = name, mails, []

    async def inbox(self, limit=5):
        return self.mails[:limit]

    async def read(self, mid):
        return f"{self.name}:{mid}"

    async def send(self, to, subject, body):
        self.sent.append(to)

    async def reply(self, mid, body):
        self.sent.append(mid)


async def test_agenda_merges_sorted_and_skips_failing_provider():
    hub = IntegrationHub(
        [
            Cal("google", [_ev("g", 15, "google")]),
            Cal("microsoft", [_ev("m", 9, "microsoft")]),
            Cal("x", [], fail=True),
        ],
        [],
    )
    assert [e.id for e in await hub.agenda(date(2026, 10, 17))] == ["m", "g"]


async def test_inbox_merges_newest_first_with_namespaced_ids():
    hub = IntegrationHub(
        [],
        [
            Mail("google", [_mail("a", 8, "google")]),
            Mail("microsoft", [_mail("b", 9, "microsoft")]),
        ],
    )
    mails = await hub.inbox(5)
    assert [hub.mail_ref(m) for m in mails] == ["microsoft:b", "google:a"]


async def test_read_and_reply_route_by_namespace():
    g, m = Mail("google", []), Mail("microsoft", [])
    hub = IntegrationHub([], [g, m])
    assert await hub.read("microsoft:x1") == "microsoft:x1"
    await hub.reply("google:m9", "ok")
    assert g.sent == ["m9"]


async def test_send_uses_default_or_named_provider():
    g, m = Mail("google", []), Mail("microsoft", [])
    hub = IntegrationHub([], [g, m], default="microsoft")
    await hub.send("a@x.pt", "s", "b")
    await hub.send("b@x.pt", "s", "b", provider="google")
    assert m.sent == ["a@x.pt"] and g.sent == ["b@x.pt"]


async def test_unknown_reference_raises():
    hub = IntegrationHub([], [Mail("google", [])])
    with pytest.raises(ValueError):
        await hub.read("outlook:1")


def test_status():
    hub = IntegrationHub([Cal("google", [])], [Mail("google", [])])
    assert hub.connected == ["google"]
