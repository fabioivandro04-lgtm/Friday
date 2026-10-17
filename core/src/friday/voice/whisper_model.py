"""Um só Whisper carregado para toda a Friday (app, chamadas e notas de voz)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


def load_whisper(name: str, device: str) -> Any:
    from faster_whisper import WhisperModel

    compute = "int8_float16" if device == "cuda" else "int8"
    return WhisperModel(name, device=device, compute_type=compute)


class SharedWhisper:
    def __init__(
        self, name: str, device: str, loader: Callable[[str, str], Any] = load_whisper
    ) -> None:
        self._name, self._device, self._loader = name, device, loader
        self._model: Any = None
        self._lock = threading.Lock()

    def get(self) -> Any:
        with self._lock:
            if self._model is None:
                self._model = self._loader(self._name, self._device)
            return self._model
