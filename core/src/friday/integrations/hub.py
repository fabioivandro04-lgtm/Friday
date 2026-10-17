"""Junta Google e Microsoft: uma só agenda e uma só caixa de entrada."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from friday.integrations.models import CalendarEvent, CalendarProvider, MailProvider, MailSummary

logger = logging.getLogger("friday.integrations")


class IntegrationHub:
    def __init__(
        self,
        calendars: list[CalendarProvider],
        mailboxes: list[MailProvider],
        default: str | None = None,
    ) -> None:
        self._calendars = calendars
        self._mailboxes = mailboxes
        self._default = default

    @property
    def connected(self) -> list[str]:
        return sorted({p.name for p in [*self._calendars, *self._mailboxes]})

    async def _gather(self, calls) -> list:
        results = await asyncio.gather(*calls, return_exceptions=True)
        out = []
        for r in results:
            if isinstance(r, BaseException):
                logger.warning(
                    "Integração falhou: %s", r
                )  # um fornecedor em baixo não apaga os outros
            else:
                out.extend(r)
        return out

    async def agenda(self, day: date) -> list[CalendarEvent]:
        events = await self._gather([c.list_events(day) for c in self._calendars])
        return sorted(events, key=lambda e: (not e.all_day, e.start))

    async def inbox(self, limit: int = 5) -> list[MailSummary]:
        mails = await self._gather([m.inbox(limit) for m in self._mailboxes])
        return sorted(mails, key=lambda m: m.received, reverse=True)[:limit]

    @staticmethod
    def mail_ref(mail: MailSummary) -> str:
        return f"{mail.provider}:{mail.id}"

    def _pick(self, providers: list, name: str | None):
        if not providers:
            raise ValueError("Nenhuma conta ligada (python -m friday connect google|microsoft).")
        wanted = name or self._default
        for p in providers:
            if wanted is None or p.name == wanted:
                return p
        raise ValueError(f"Conta desconhecida: {wanted}")

    def _resolve(self, ref: str) -> tuple[MailProvider, str]:
        name, _, message_id = ref.partition(":")
        if not message_id:
            raise ValueError(f"Referência de email inválida: {ref}")
        return self._pick(self._mailboxes, name), message_id

    async def read(self, ref: str) -> str:
        provider, message_id = self._resolve(ref)
        return await provider.read(message_id)

    async def reply(self, ref: str, body: str) -> None:
        provider, message_id = self._resolve(ref)
        await provider.reply(message_id, body)

    async def send(self, to: str, subject: str, body: str, provider: str | None = None) -> None:
        await self._pick(self._mailboxes, provider).send(to, subject, body)

    async def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str],
        provider: str | None = None,
    ) -> CalendarEvent:
        return await self._pick(self._calendars, provider).create_event(
            title, start, end, attendees
        )
