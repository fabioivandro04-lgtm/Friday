from friday.__main__ import build_services
from friday.config import (
    BriefingConfig,
    Config,
    MemoryConfig,
    TelegramConfig,
    TtsConfig,
    TwilioConfig,
)

from .memory.conftest import FakeEmbedder


def _cfg(tmp_path, **kw):
    return Config(
        tts=TtsConfig("pt_PT-x", "en_GB-x"),
        memory=MemoryConfig(db_path=str(tmp_path / "f.db")),
        **kw,
    )


def test_minimal_setup_has_scheduler_and_all_tools(tmp_path):
    s = build_services(_cfg(tmp_path), embedder=FakeEmbedder())
    names = {t["function"]["name"] for t in s.deps.registry.schemas()}
    assert {
        "web_search",
        "remember",
        "recall",
        "agenda",
        "create_event",
        "inbox",
        "send_email",
        "weather",
        "remind_me",
        "list_reminders",
    } <= names
    assert s.telegram is None and s.twilio is None
    assert len(s.background) == 1  # só o agendador
    assert s.deps.announcer is not None


def test_telegram_needs_token(tmp_path):
    cfg = _cfg(tmp_path, telegram=TelegramConfig(enabled=True, allowed_chat_id=42))
    assert build_services(cfg, embedder=FakeEmbedder()).telegram is None
    cfg = _cfg(tmp_path, telegram=TelegramConfig(enabled=True, allowed_chat_id=42, token="T"))
    s = build_services(cfg, embedder=FakeEmbedder())
    assert s.telegram is not None and len(s.background) == 2


def test_twilio_gateway_and_call_briefing(tmp_path):
    tw = TwilioConfig(
        enabled=True,
        account_sid="AC1",
        from_number="+1",
        to_number="+2",
        public_url="https://pc.ts.net",
        auth_token="x",
    )
    cfg = _cfg(tmp_path, twilio=tw, briefing=BriefingConfig(enabled=True, channel="call"))
    s = build_services(cfg, embedder=FakeEmbedder())
    assert s.twilio is not None
    names = {t["function"]["name"] for t in s.deps.registry.schemas()}
    assert "call_me" in names
