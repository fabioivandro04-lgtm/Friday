"""Modelo comum para agenda e email, seja Google ou Microsoft."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

Provider = Literal["google", "microsoft"]


class TokenSource(Protocol):
    async def get_token(self) -> str: ...


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    provider: Provider
    location: str = ""
    all_day: bool = False


@dataclass(frozen=True)
class MailSummary:
    id: str
    sender: str
    subject: str
    snippet: str
    received: datetime
    provider: Provider
    unread: bool = True
    important: bool = False


class CalendarProvider(Protocol):
    name: Provider

    async def list_events(self, day) -> list[CalendarEvent]: ...

    async def create_event(
        self, title: str, start: datetime, end: datetime, attendees: list[str]
    ) -> CalendarEvent: ...


class MailProvider(Protocol):
    name: Provider

    async def inbox(self, limit: int = 5) -> list[MailSummary]: ...

    async def read(self, message_id: str) -> str: ...

    async def send(self, to: str, subject: str, body: str) -> None: ...

    async def reply(self, message_id: str, body: str) -> None: ...
