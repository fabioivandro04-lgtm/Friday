"""Carrega a configuração da Friday a partir de friday.toml (+ segredos do ambiente)."""

from __future__ import annotations

import logging
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
    # "local" (Ollama, grátis) ou "cloud" (OpenRouter, precisa de chave).
    provider: str = "local"
    local_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434/v1"
    cloud_model: str | None = None
    cloud_api_key: str | None = None
    slow_threshold_s: float = 2.0


@dataclass(frozen=True)
class TtsConfig:
    # IDs de vozes Piper (ex.: "pt_PT-tugão-medium"); descarregadas para download_dir.
    voice_pt: str
    voice_en: str
    download_dir: str = "models/piper"


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
class WakeConfig:
    # Modo "sempre à escuta": só responde depois de ouvir uma destas frases.
    enabled: bool = False
    phrases: list[str] = field(default_factory=lambda: ["friday"])
    window_s: float = 15.0


@dataclass(frozen=True)
class IntegrationsConfig:
    timezone: str = "Europe/Lisbon"
    # Tokens do Google/Microsoft e o client_secret.json do Google (fora do Git).
    secrets_dir: str = "secrets"
    microsoft_client_id: str | None = None
    # Conta usada para enviar/marcar quando não se diz qual: "google" ou "microsoft".
    default_provider: str | None = None


@dataclass(frozen=True)
class Config:
    tts: TtsConfig
    stt: SttConfig = field(default_factory=SttConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)


logger = logging.getLogger("friday.config")

# Segredos nunca vêm do TOML (que pode acabar no Git), só do ambiente / .env.
_SECRET_KEYS = {"cloud_api_key", "token"}


def _section(cls: type, data: Mapping[str, Any], name: str = "") -> dict[str, Any]:
    allowed = {f.name for f in fields(cls)} - _SECRET_KEYS
    for key in data:
        if key not in allowed and key not in _SECRET_KEYS:
            logger.warning("friday.toml: chave desconhecida %s.%s (ignorada)", name, key)
    return {k: v for k, v in data.items() if k in allowed}


def load_config(path: Path, env: Mapping[str, str] = os.environ) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))

    tts_raw = raw.get("tts", {})
    for key in ("voice_pt", "voice_en"):
        if not tts_raw.get(key):
            raise ValueError(
                f"friday.toml: falta [tts].{key} (ID da voz Piper, ex.: pt_PT-tugão-medium)"
            )

    llm = LlmConfig(
        **_section(LlmConfig, raw.get("llm", {}), "llm"),
        cloud_api_key=env.get("OPENROUTER_API_KEY") or None,
    )
    server = ServerConfig(
        **_section(ServerConfig, raw.get("server", {}), "server"),
        token=env.get("FRIDAY_TOKEN") or None,
    )
    return Config(
        tts=TtsConfig(**_section(TtsConfig, tts_raw, "tts")),
        stt=SttConfig(**_section(SttConfig, raw.get("stt", {}), "stt")),
        llm=llm,
        server=server,
        memory=MemoryConfig(**_section(MemoryConfig, raw.get("memory", {}), "memory")),
        wake=WakeConfig(**_section(WakeConfig, raw.get("wake", {}), "wake")),
        integrations=IntegrationsConfig(
            **_section(IntegrationsConfig, raw.get("integrations", {}), "integrations")
        ),
    )
