"""Transcrição de ficheiros de áudio (notas de voz do Telegram)."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Callable
from typing import Any


def _load_whisper(name: str, device: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(
        name, device=device, compute_type="int8_float16" if device == "cuda" else "int8"
    )


class FileTranscriber:
    """Carrega o Whisper só na primeira nota de voz (não ocupa VRAM sem necessidade)."""

    def __init__(
        self, model: str, device: str, loader: Callable[[str, str], Any] = _load_whisper
    ) -> None:
        self._name, self._device, self._loader = model, device, loader
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _run(self, data: bytes) -> str:
        # O faster-whisper descodifica OGG/Opus com o PyAV a partir de um ficheiro em memória.
        segments, _ = self._model.transcribe(io.BytesIO(data), vad_filter=True)
        return "".join(s.text for s in segments).strip()

    async def __call__(self, data: bytes) -> str:
        async with self._lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._loader, self._name, self._device)
            return await asyncio.to_thread(self._run, data)
