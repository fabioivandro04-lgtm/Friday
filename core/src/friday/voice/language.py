"""Escolhe a língua da resposta (e da voz) a partir da deteção do Whisper."""

from __future__ import annotations

from typing import Literal

Lang = Literal["pt", "en"]

_MIN_PROBABILITY = 0.6
_MIN_WORDS = 3


def choose_language(detected: str | None, probability: float, text: str, previous: Lang) -> Lang:
    # Frases curtas ("sim", "ok") e deteções fracas trocariam de voz sem razão.
    if detected not in ("pt", "en"):
        return previous
    if probability < _MIN_PROBABILITY or len(text.split()) < _MIN_WORDS:
        return previous
    return detected
