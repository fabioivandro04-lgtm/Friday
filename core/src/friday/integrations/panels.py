"""Mantém os painéis Agenda e Email do HUD atualizados."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from friday.integrations.hub import IntegrationHub

logger = logging.getLogger("friday.integrations")
Emit = Callable[[dict[str, Any]], Awaitable[None]]


class PanelFeeder:
    def __init__(
        self,
        hub: IntegrationHub,
        emit: Emit,
        now: Callable[[], datetime],
        interval_s: float = 300.0,
    ) -> None:
        self._hub, self._emit, self._now, self._interval = hub, emit, now, interval_s

    async def refresh(self) -> None:
        connected = bool(self._hub.connected)
        agenda, inbox = [], []
        if connected:
            events = await self._hub.agenda(self._now().date())
            agenda = [
                {
                    "time": "dia todo" if e.all_day else f"{e.start:%H:%M}",
                    "title": e.title,
                    "location": e.location,
                }
                for e in events
            ]
            inbox = [
                {"ref": self._hub.mail_ref(m), "sender": m.sender, "subject": m.subject}
                for m in await self._hub.inbox(5)
            ]
        await self._emit({"type": "agenda", "data": {"connected": connected, "items": agenda}})
        await self._emit({"type": "inbox", "data": {"connected": connected, "items": inbox}})

    async def run(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as e:  # noqa: BLE001 — um painel em baixo não pode parar a voz
                logger.warning("Painéis: %s", e)
            await asyncio.sleep(self._interval)
