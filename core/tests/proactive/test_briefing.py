from datetime import datetime
from zoneinfo import ZoneInfo

from friday.integrations.hub import IntegrationHub
from friday.proactive.briefing import Briefing

from ..integrations.test_hub import Cal, Mail, _ev, _mail

TZ = ZoneInfo("Europe/Lisbon")
NOW = datetime(2026, 10, 17, 8, 0, tzinfo=TZ)


class Client:
    def __init__(self, fail=False):
        self.fail = fail
        self.prompt = None

    async def complete(self, messages, tools):
        if self.fail:
            raise ConnectionError("x")
        self.prompt = messages[-1]["content"]
        return {"content": "<think>.</think>Bom dia, Fábio!", "tool_calls": []}


async def weather():
    return "Lisboa, hoje: céu limpo, máxima 22°C."


def _hub():
    return IntegrationHub(
        [Cal("google", [_ev("g", 10, "google")])], [Mail("google", [_mail("m1", 7, "google")])]
    )


async def test_briefing_uses_agenda_mail_and_weather():
    c = Client()
    text = await Briefing(_hub(), weather, c, TZ, now=lambda: NOW).build()
    assert text == "Bom dia, Fábio!"
    assert "ev g" in c.prompt and "s m1" in c.prompt and "céu limpo" in c.prompt


async def test_briefing_falls_back_to_raw_facts_when_llm_fails():
    text = await Briefing(_hub(), weather, Client(fail=True), TZ, now=lambda: NOW).build()
    assert "ev g" in text and "céu limpo" in text
