from friday.config import LlmConfig
from friday.llm.providers import (
    SlowResponseWatch,
    cloud_endpoint,
    filler_phrase,
    local_endpoint,
    select_endpoint,
)


def test_local_endpoint_disables_thinking():
    ep = local_endpoint(LlmConfig())
    assert ep.base_url == "http://localhost:11434/v1"
    assert ep.model == "qwen3:8b"
    assert ep.api_key == "ollama"
    assert ep.extra_body == {"think": False}


def test_cloud_endpoint_none_without_key():
    assert cloud_endpoint(LlmConfig(cloud_model="a/b")) is None


def test_cloud_endpoint_none_without_model():
    assert cloud_endpoint(LlmConfig(cloud_api_key="k")) is None


def test_cloud_endpoint_with_key():
    ep = cloud_endpoint(LlmConfig(cloud_model="a/b", cloud_api_key="k"))
    assert ep.base_url == "https://openrouter.ai/api/v1"
    assert ep.api_key == "k" and ep.model == "a/b"
    assert ep.extra_body == {"provider": {"sort": "latency"}}


def test_filler_phrases():
    assert filler_phrase("pt") == "Deixa-me ver…"
    assert filler_phrase("en") == "Let me check…"


def test_filler_said_once_after_threshold():
    t = [0.0]
    w = SlowResponseWatch(2.0, clock=lambda: t[0])
    w.start()
    t[0] = 1.9
    assert w.should_say_filler() is False
    t[0] = 2.1
    assert w.should_say_filler() is True
    assert w.should_say_filler() is False


def test_no_filler_after_first_token():
    t = [0.0]
    w = SlowResponseWatch(2.0, clock=lambda: t[0])
    w.start()
    t[0] = 0.5
    w.first_token()
    t[0] = 5.0
    assert w.should_say_filler() is False


def test_no_filler_before_start():
    assert SlowResponseWatch(2.0, clock=lambda: 99.0).should_say_filler() is False


def test_select_endpoint_local_by_default():
    cfg = LlmConfig(cloud_model="a/b", cloud_api_key="k")
    assert select_endpoint(cfg).base_url == "http://localhost:11434/v1"


def test_select_endpoint_cloud_when_chosen():
    cfg = LlmConfig(provider="cloud", cloud_model="a/b", cloud_api_key="k")
    assert select_endpoint(cfg).base_url == "https://openrouter.ai/api/v1"


def test_select_endpoint_falls_back_to_local_without_key():
    assert select_endpoint(LlmConfig(provider="cloud", cloud_model="a/b")).model == "qwen3:8b"
