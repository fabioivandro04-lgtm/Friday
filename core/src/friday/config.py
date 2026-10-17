"""Carrega a configuração da Friday a partir de friday.toml (+ segredos do ambiente)."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SttConfig:
    model: str = "large-v3-turbo"
    device: str = "cuda"


@dataclass(frozen=True)
class LlmConfig:
    local_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434/v1"
    cloud_model: str | None = None
    cloud_api_key: str | None = None
    slow_threshold_s: float = 2.0


@dataclass(frozen=True)
class TtsConfig:
    voice_pt: str
    voice_en: str


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    token: str | None = None


@dataclass(frozen=True)
class MemoryConfig:
    db_path: str = "friday.db"
    min_similarity: float = 0.35


@dataclass(frozen=True)
class Config:
    tts: TtsConfig
    stt: SttConfig = field(default_factory=SttConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


# Segredos nunca vêm do TOML (que pode acabar no Git), só do ambiente / .env.
_SECRET_KEYS = {"cloud_api_key", "token"}


def _section(cls: type, data: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {f.name for f in fields(cls)} - _SECRET_KEYS
    return {k: v for k, v in data.items() if k in allowed}


def load_config(path: Path, env: Mapping[str, str] = os.environ) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))

    tts_raw = raw.get("tts", {})
    for key in ("voice_pt", "voice_en"):
        if not tts_raw.get(key):
            raise ValueError(f"friday.toml: falta [tts].{key} (caminho da voz Piper)")

    llm = LlmConfig(
        **_section(LlmConfig, raw.get("llm", {})),
        cloud_api_key=env.get("OPENROUTER_API_KEY") or None,
    )
    server = ServerConfig(
        **_section(ServerConfig, raw.get("server", {})),
        token=env.get("FRIDAY_TOKEN") or None,
    )
    return Config(
        tts=TtsConfig(**_section(TtsConfig, tts_raw)),
        stt=SttConfig(**_section(SttConfig, raw.get("stt", {}))),
        llm=llm,
        server=server,
        memory=MemoryConfig(**_section(MemoryConfig, raw.get("memory", {}))),
    )
