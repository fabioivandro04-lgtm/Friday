"""Onde a Friday "pensa": Ollama local (padrão) ou OpenRouter (opcional)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from friday.config import LlmConfig

OPENROUTER_URL = "https://openrouter.ai/api/v1"
_FILLERS = {"pt": "Deixa-me ver…", "en": "Let me check…"}


@dataclass(frozen=True)
class LlmEndpoint:
    """Um endpoint compatível com a API da OpenAI."""

    base_url: str
    model: str
    api_key: str
    extra_body: dict[str, Any] = field(default_factory=dict)


def local_endpoint(cfg: LlmConfig) -> LlmEndpoint:
    # "think": False desliga o raciocínio do Qwen3, que só atrasaria a voz.
    return LlmEndpoint(cfg.ollama_url, cfg.local_model, "ollama", {"think": False})


def cloud_endpoint(cfg: LlmConfig) -> LlmEndpoint | None:
    if not (cfg.cloud_model and cfg.cloud_api_key):
        return None
    return LlmEndpoint(
        OPENROUTER_URL, cfg.cloud_model, cfg.cloud_api_key, {"provider": {"sort": "latency"}}
    )


def select_endpoint(cfg: LlmConfig) -> LlmEndpoint:
    cloud = cloud_endpoint(cfg) if cfg.provider == "cloud" else None
    return cloud or local_endpoint(cfg)


def filler_phrase(lang: Literal["pt", "en"]) -> str:
    return _FILLERS[lang]


class SlowResponseWatch:
    """Diz quando a Friday deve preencher o silêncio (uma única vez por resposta)."""

    def __init__(self, threshold_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._threshold_s = threshold_s
        self._clock = clock
        self._started_at: float | None = None
        self._done = False

    def start(self) -> None:
        self._started_at = self._clock()
        self._done = False

    def first_token(self) -> None:
        self._done = True

    def should_say_filler(self) -> bool:
        if self._done or self._started_at is None:
            return False
        if self._clock() - self._started_at >= self._threshold_s:
            self._done = True
            return True
        return False
