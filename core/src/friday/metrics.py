"""Latência por etapa (fim da fala → primeiro som) e uso de VRAM."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

Stage = Literal["speech_end", "stt_done", "llm_first_token", "tts_first_audio"]


class TurnTimer:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._marks: dict[str, float] = {}

    def mark(self, stage: Stage) -> None:
        if stage == "speech_end":
            self._marks = {"speech_end": self._clock()}
        elif "speech_end" in self._marks:
            self._marks.setdefault(stage, self._clock())

    def report(self) -> dict[str, int]:
        start = self._marks.get("speech_end")
        if start is None:
            return {}
        out = {k: round((v - start) * 1000) for k, v in self._marks.items() if k != "speech_end"}
        if "tts_first_audio" in out:
            out["total_ms"] = out["tts_first_audio"]
        return out

    def reset(self) -> None:
        self._marks = {}


def vram_used_gb() -> float | None:
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
            return round(info.used / 1024**3, 1)
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        return None
