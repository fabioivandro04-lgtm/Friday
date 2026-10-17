"""Palavra de ativação por texto: a Friday só responde depois de ouvir o nome dela."""

from __future__ import annotations

import re
import unicodedata


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class WakeGate:
    """Deixa passar a conversa quando a Friday está acordada.

    Quem decide se está acordada é o Pipecat (WakePhraseUserTurnStartStrategy,
    via `set_awake`); aqui só se reconhece o nome na própria frase, porque o
    cérebro vê a transcrição antes de o Pipecat a analisar.
    """

    def __init__(self, phrases: list[str]) -> None:
        self._patterns = [re.compile(rf"\b{re.escape(_normalise(p))}\b") for p in phrases]
        self._awake = False

    def set_awake(self, awake: bool) -> None:
        self._awake = awake

    def admit(self, text: str) -> bool:
        norm = _normalise(text)
        return self._awake or any(p.search(norm) for p in self._patterns)
