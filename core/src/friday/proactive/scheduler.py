"""Agendador: lembretes e resumo da manhã, entregues no Telegram e em voz."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from typing import Protocol

from friday.config import BriefingConfig
from friday.proactive.reminders import ReminderStore

logger = logging.getLogger("friday.scheduler")
Speak = Callable[[str], Awaitable[None]]
# Se o PC estava desligado à hora do resumo, só o envia até esta janela depois.
_BRIEFING_WINDOW = timedelta(hours=2)


class Channel(Protocol):
    async def notify(self, text: str) -> None: ...


class BriefingSource(Protocol):
    async def build(self) -> str: ...


class Announcer:
    """A sessão de voz ativa (se houver) regista aqui como dizer avisos em voz alta."""

    def __init__(self) -> None:
        self._speak: Speak | None = None

    def attach(self, speak: Speak) -> None:
        self._speak = speak

    def detach(self, speak: Speak) -> None:
        if self._speak is speak:
            self._speak = None

    async def say(self, text: str) -> bool:
        if self._speak is None:
            return False
        await self._speak(text)
        return True


class Notifier:
    def __init__(self, telegram: Channel | None, announcer: Announcer) -> None:
        self._telegram = telegram
        self._announcer = announcer

    async def notify(self, text: str) -> None:
        for name, send in (
            ("telegram", self._telegram and self._telegram.notify),
            ("voz", self._announcer.say),
        ):
            if not send:
                continue
            try:
                await send(text)
            except Exception as e:  # noqa: BLE001 — um canal em baixo não cala os outros
                logger.warning("Aviso por %s falhou: %s", name, e)


class Scheduler:
    def __init__(
        self,
        reminders: ReminderStore,
        notifier: Notifier,
        briefing: BriefingSource | None,
        briefing_cfg: BriefingConfig,
        now: Callable[[], datetime],
        deliver_briefing: Callable[[str], Awaitable[None]] | None = None,
        interval_s: float = 30.0,
    ) -> None:
        self._reminders = reminders
        self._notifier = notifier
        self._briefing = briefing
        self._cfg = briefing_cfg
        self._now = now
        self._deliver = deliver_briefing or notifier.notify
        self._interval = interval_s
        self._last_briefing = None

    async def tick(self) -> None:
        now = self._now()
        for r in await asyncio.to_thread(self._reminders.due, now):
            await self._notifier.notify(f"Lembrete: {r.text}")
            await asyncio.to_thread(self._reminders.mark_done, r.id)
        if self._briefing_due(now):
            self._last_briefing = now.date()
            await self._deliver(await self._briefing.build())

    def _briefing_due(self, now: datetime) -> bool:
        if not (self._cfg.enabled and self._briefing) or self._last_briefing == now.date():
            return False
        if self._cfg.weekdays_only and now.weekday() >= 5:
            return False
        hour, minute = (int(x) for x in self._cfg.time.split(":"))
        at = datetime.combine(now.date(), time(hour, minute), tzinfo=now.tzinfo)
        return at <= now <= at + _BRIEFING_WINDOW

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning("Agendador: %s", e)
            await asyncio.sleep(self._interval)
