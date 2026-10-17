"""Palavra de ativação por texto: a Friday só responde depois de ouvir o nome dela."""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class WakeGate:
    """Abre ao ouvir uma das frases e fica aberto `window_s` desde a última frase dita."""

    def __init__(
        self, phrases: list[str], window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._patterns = [re.compile(rf"\b{re.escape(_normalise(p))}\b") for p in phrases]
        self._window_s = window_s
        self._clock = clock
        self._open_until = float("-inf")

    def feed(self, text: str) -> bool:
        now = self._clock()
        norm = _normalise(text)
        if any(p.search(norm) for p in self._patterns) or now <= self._open_until:
            self._open_until = now + self._window_s
            return True
        return False
