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

    async def notify(self, text: str) -> bool:
        """Devolve True se pelo menos um canal entregou o aviso."""
        delivered = False
        if self._telegram is not None:
            try:
                await self._telegram.notify(text)
                delivered = True
            except Exception as e:  # noqa: BLE001 — um canal em baixo não cala os outros
                logger.warning("Aviso por Telegram falhou: %s", e)
        try:
            delivered = await self._announcer.say(text) or delivered
        except Exception as e:  # noqa: BLE001
            logger.warning("Aviso por voz falhou: %s", e)
        return delivered


class Scheduler:
    def __init__(
        self,
        reminders: ReminderStore,
        notifier: Notifier,
        briefing: BriefingSource | None,
        briefing_cfg: BriefingConfig,
        now: Callable[[], datetime],
        deliver_briefing: Callable[[str], Awaitable[object]] | None = None,
        interval_s: float = 30.0,
    ) -> None:
        self._reminders = reminders
        self._notifier = notifier
        self._briefing = briefing
        self._cfg = briefing_cfg
        self._now = now
        self._deliver = deliver_briefing
        self._interval = interval_s

    async def tick(self) -> None:
        now = self._now()
        for r in await asyncio.to_thread(self._reminders.due, now):
            # Só fica feito se alguém o recebeu; senão volta a tentar no próximo ciclo.
            if await self._notifier.notify(f"Lembrete: {r.text}"):
                await asyncio.to_thread(self._reminders.mark_done, r.id)
        if await asyncio.to_thread(self._briefing_due, now):
            # Guardado em SQLite: reiniciar o Core às 8h05 não repete o resumo.
            await asyncio.to_thread(
                self._reminders.set_state, "last_briefing", now.date().isoformat()
            )
            text = await self._briefing.build()
            if self._deliver is not None:
                try:
                    await self._deliver(text)
                    return
                except Exception as e:  # noqa: BLE001 — ex.: Twilio em baixo
                    logger.warning("Resumo por chamada falhou (%s); a enviar por mensagem.", e)
            await self._notifier.notify(text)

    def _briefing_due(self, now: datetime) -> bool:
        if not (self._cfg.enabled and self._briefing):
            return False
        if self._reminders.get_state("last_briefing") == now.date().isoformat():
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
