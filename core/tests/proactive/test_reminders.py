from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from friday.proactive.reminders import ReminderStore, make_reminder_tools
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import ToolRegistry, execute

TZ = ZoneInfo("Europe/Lisbon")
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=TZ)


def test_store_due_and_done(tmp_path):
    store = ReminderStore(str(tmp_path / "r.db"))
    a = store.add(NOW + timedelta(minutes=5), "beber água")
    store.add(NOW + timedelta(hours=2), "ligar à mãe")
    assert store.due(NOW) == []
    [due] = store.due(NOW + timedelta(minutes=6))
    assert due.id == a and due.text == "beber água"
    store.mark_done(a)
    assert store.due(NOW + timedelta(minutes=6)) == []
    assert [r.text for r in store.upcoming(NOW)] == ["ligar à mãe"]


async def test_remind_me_tool_relative_and_absolute(tmp_path):
    store = ReminderStore(str(tmp_path / "r.db"))
    reg, conf = ToolRegistry(), ConfirmationManager()
    for t in make_reminder_tools(store, TZ, now=lambda: NOW):
        reg.register(t)
    out = await execute(reg, conf, "remind_me", {"text": "tirar o bolo", "in_minutes": 30})
    assert "09:30" in out
    out = await execute(reg, conf, "remind_me", {"text": "reunião", "at": "2026-10-17T15:00"})
    assert "15:00" in out
    bad = await execute(reg, conf, "remind_me", {"text": "x", "at": "2026-10-17T08:00"})
    assert bad.startswith("ERRO")  # no passado
    listing = await execute(reg, conf, "list_reminders", {})
    assert "tirar o bolo" in listing and "reunião" in listing
