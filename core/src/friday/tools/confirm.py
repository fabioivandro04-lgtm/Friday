"""Ações pendentes: nada que altere algo corre sem um "sim" claro."""

from __future__ import annotations

import re
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from friday.tools.registry import Tool

Resolution = Literal["confirmed", "rejected", "unclear"]

_UNCLEAR = {"nao sei", "talvez", "nao tenho a certeza", "maybe", "not sure", "i dont know"}
_REJECT = {"nao", "cancela", "cancelar", "para", "no", "nope", "cancel", "stop"}
_CONFIRM = {"sim", "confirmo", "confirma", "envia", "podes", "pode", "claro", "yes", "ok", "go"}


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]+", " ", text).strip()


def parse_confirmation(answer: str) -> Resolution:
    norm = _normalise(answer)
    if not norm or any(phrase in norm for phrase in _UNCLEAR):
        return "unclear"
    words = set(norm.split())
    if words & _REJECT:
        return "rejected"
    if words & _CONFIRM:
        return "confirmed"
    return "unclear"


@dataclass
class PendingAction:
    id: str
    tool: str
    args: dict[str, Any]
    summary: str
    created_at: float = field(default=0.0)


class ConfirmationManager:
    """Guarda no máximo uma ação pendente, que expira ao fim de `ttl_s`."""

    def __init__(self, ttl_s: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._pending: PendingAction | None = None

    def propose(self, tool: Tool, args: dict[str, Any]) -> PendingAction:
        summary = tool.summary(args) if tool.summary else f"Executar {tool.name}"
        self._pending = PendingAction(
            id=uuid.uuid4().hex,
            tool=tool.name,
            args=dict(args),
            summary=summary,
            created_at=self._clock(),
        )
        return self._pending

    def pending(self) -> PendingAction | None:
        if self._pending and self._clock() - self._pending.created_at > self._ttl_s:
            self._pending = None
        return self._pending

    def resolve(self, answer: str) -> Resolution:
        """Interpreta a resposta falada; limpa a ação se confirmada ou rejeitada.

        Quem chama lê `pending()` antes, para saber que ação executar.
        """
        result = parse_confirmation(answer)
        if result != "unclear":
            self._pending = None
        return result

    def cancel(self) -> None:
        self._pending = None

    def confirm_by_id(self, action_id: str) -> PendingAction | None:
        action = self.pending()
        if action is None or action.id != action_id:
            return None
        self._pending = None
        return action
