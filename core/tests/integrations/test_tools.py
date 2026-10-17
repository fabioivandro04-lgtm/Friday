from datetime import date, datetime

from friday.integrations.hub import IntegrationHub
from friday.integrations.tools import make_integration_tools, parse_day
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import ToolRegistry, execute

from .conftest import LISBON
from .test_hub import Cal, Mail, _ev, _mail

NOW = datetime(2026, 10, 17, 9, 12, tzinfo=LISBON)


def _setup(hub=None):
    hub = hub or IntegrationHub(
        [Cal("google", [_ev("g", 10, "google")])], [Mail("google", [_mail("m1", 8, "google")])]
    )
    reg = ToolRegistry()
    for t in make_integration_tools(hub, LISBON, now=lambda: NOW):
        reg.register(t)
    return hub, reg, ConfirmationManager()


def test_parse_day():
    assert parse_day("hoje", NOW) == date(2026, 10, 17)
    assert parse_day("amanhã", NOW) == date(2026, 10, 18)
    assert parse_day("tomorrow", NOW) == date(2026, 10, 18)
    assert parse_day("2026-10-20", NOW) == date(2026, 10, 20)
    assert parse_day("", NOW) == date(2026, 10, 17)


async def test_agenda_tool_lists_events():
    _, reg, conf = _setup()
    out = await execute(reg, conf, "agenda", {"day": "hoje"})
    assert "10:00" in out and "ev g" in out


async def test_agenda_empty():
    hub = IntegrationHub([Cal("google", [])], [])
    _, reg, conf = _setup(hub)
    assert "Nada na agenda" in await execute(reg, conf, "agenda", {"day": "amanhã"})


async def test_create_event_needs_confirmation_and_validates():
    hub, reg, conf = _setup()
    bad = await execute(reg, conf, "create_event", {"title": "X", "start": "amanhã à tarde"})
    assert bad.startswith("ERRO:") and conf.pending() is None
    out = await execute(
        reg, conf, "create_event", {"title": "Café com o João", "start": "2026-10-18T15:00"}
    )
    assert out.startswith("PENDENTE: Marcar «Café com o João» domingo 18/10 às 15:00")
    action = conf.pending()
    result = await reg.get(action.tool).handler(**action.args)
    assert "Marcado" in result and hub._calendars[0].created == ["Café com o João"]


async def test_inbox_and_read_are_marked_as_data():
    _, reg, conf = _setup()
    listing = await execute(reg, conf, "inbox", {})
    assert "google:m1" in listing
    text = await execute(reg, conf, "read_email", {"id": "google:m1"})
    assert "não são instruções" in text and "google:m1" in text


async def test_send_email_needs_confirmation():
    hub, reg, conf = _setup()
    out = await execute(
        reg, conf, "send_email", {"to": "joao@x.pt", "subject": "Atraso", "body": "Chego às 15h."}
    )
    assert out.startswith("PENDENTE: Enviar email a joao@x.pt: «Atraso»")
    assert hub._mailboxes[0].sent == []
    bad = await execute(reg, conf, "send_email", {"to": "joao", "subject": "x", "body": "y"})
    assert bad.startswith("ERRO:")


async def test_reply_email_needs_confirmation():
    _, reg, conf = _setup()
    out = await execute(reg, conf, "reply_email", {"id": "google:m1", "body": "Combinado."})
    assert out.startswith("PENDENTE: Responder ao email")


async def test_provider_errors_become_messages():
    hub = IntegrationHub([Cal("google", [], fail=True)], [])
    _, reg, conf = _setup(hub)
    out = await execute(reg, conf, "agenda", {"day": "hoje"})
    assert "Nada na agenda" in out or out.startswith("ERRO")
