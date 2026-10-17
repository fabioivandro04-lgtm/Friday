"""Mensagens que o Core envia à interface (via mensagens de servidor RTVI)."""

from __future__ import annotations

from typing import Any, Literal

from friday.tools.confirm import PendingAction


def _event(type_: str, **data: Any) -> dict[str, Any]:
    return {"type": type_, "data": data}


def state(value: Literal["listening", "thinking", "speaking"]) -> dict[str, Any]:
    return _event("state", value=value)


def transcript(role: Literal["user", "assistant"], text: str) -> dict[str, Any]:
    return _event("transcript", role=role, text=text)


def confirm_request(action: PendingAction) -> dict[str, Any]:
    return _event("confirm_request", id=action.id, summary=action.summary)


def confirm_cleared(action_id: str) -> dict[str, Any]:
    return _event("confirm_cleared", id=action_id)


def system(
    model: str,
    voice: str,
    latency_ms: int | None,
    vram_used_gb: float | None,
    error: str | None = None,
) -> dict[str, Any]:
    return _event(
        "system",
        model=model,
        voice=voice,
        latency_ms=latency_ms,
        vram_used_gb=vram_used_gb,
        error=error,
    )
