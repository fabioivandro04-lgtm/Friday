from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from friday.config import BriefingConfig
from friday.proactive.reminders import ReminderStore
from friday.proactive.scheduler import Announcer, Notifier, Scheduler

TZ = ZoneInfo("Europe/Lisbon")


class Sink:
    def __init__(self):
        self.messages = []

    async def notify(self, text):
        self.messages.append(text)


class FakeBriefing:
    def __init__(self):
        self.built = 0

    async def build(self):
        self.built += 1
        return "Bom dia! Hoje tens 2 reuniões."


def _sched(tmp_path, t, briefing_cfg=None, briefing=None):
    store = ReminderStore(str(tmp_path / "r.db"))
    sink = Sink()
    sched = Scheduler(
        store,
        Notifier(telegram=sink, announcer=Announcer()),
        briefing=briefing,
        briefing_cfg=briefing_cfg or BriefingConfig(),
        now=lambda: t[0],
    )
    return store, sink, sched


async def test_due_reminder_is_sent_once(tmp_path):
    t = [datetime(2026, 10, 19, 9, 0, tzinfo=TZ)]
    store, sink, sched = _sched(tmp_path, t)
    store.add(t[0] + timedelta(minutes=1), "beber água")
    await sched.tick()
    assert sink.messages == []
    t[0] += timedelta(minutes=2)
    await sched.tick()
    await sched.tick()
    assert sink.messages == ["Lembrete: beber água"]


async def test_briefing_once_after_time_on_weekdays(tmp_path):
    cfg = BriefingConfig(enabled=True, time="08:00", weekdays_only=True)
    b = FakeBriefing()
    t = [datetime(2026, 10, 19, 7, 59, tzinfo=TZ)]  # segunda-feira
    _, sink, sched = _sched(tmp_path, t, cfg, b)
    await sched.tick()
    assert sink.messages == []
    t[0] = datetime(2026, 10, 19, 8, 0, 30, tzinfo=TZ)
    await sched.tick()
    await sched.tick()
    assert sink.messages == ["Bom dia! Hoje tens 2 reuniões."] and b.built == 1


async def test_no_briefing_on_weekend_or_when_late(tmp_path):
    cfg = BriefingConfig(enabled=True, time="08:00", weekdays_only=True)
    b = FakeBriefing()
    t = [datetime(2026, 10, 18, 8, 5, tzinfo=TZ)]  # domingo
    _, sink, sched = _sched(tmp_path, t, cfg, b)
    await sched.tick()
    t[0] = datetime(
        2026, 10, 19, 11, 0, tzinfo=TZ
    )  # segunda, mas 3h depois (Core estava desligado)
    await sched.tick()
    assert sink.messages == []


async def test_announcer_speaks_when_a_voice_session_is_active(tmp_path):
    spoken = []

    async def speak(text):
        spoken.append(text)

    ann = Announcer()
    n = Notifier(telegram=None, announcer=ann)
    await n.notify("olá")
    assert spoken == []
    ann.attach(speak)
    await n.notify("lembrete")
    ann.detach(speak)
    await n.notify("depois")
    assert spoken == ["lembrete"]


async def test_failing_channel_does_not_stop_others(tmp_path):
    class Broken:
        async def notify(self, text):
            raise RuntimeError("sem rede")

    spoken = []

    async def speak(text):
        spoken.append(text)

    ann = Announcer()
    ann.attach(speak)
    await Notifier(telegram=Broken(), announcer=ann).notify("x")
    assert spoken == ["x"]
