"""Deteta formas do português do Brasil num texto (usado nas frases de controlo)."""

from __future__ import annotations

import re

_WORDS = ["você", "ônibus", "celular", "trem", "café da manhã", "banheiro", "tela"]
_PATTERNS = [re.compile(rf"\b{re.escape(w)}\b") for w in _WORDS] + [
    # Gerúndio com estar: "estou fazendo", "está chovendo" (em PT-PT: "estou a fazer").
    re.compile(r"\b(?:estou|está|estás|estamos|estão)\s+\w+ndo\b"),
]


def find_brazilianisms(text: str) -> list[str]:
    lowered = text.lower()
    hits: list[tuple[int, str]] = []
    for pattern in _PATTERNS:
        hits.extend((m.start(), m.group(0)) for m in pattern.finditer(lowered))
    return [found for _, found in sorted(hits)]
