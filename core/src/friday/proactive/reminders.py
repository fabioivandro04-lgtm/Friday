"""Lembretes: guardados em SQLite e disparados pelo agendador."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from friday.tools.registry import Tool


@dataclass(frozen=True)
class Reminder:
    id: int
    due_at: datetime
    text: str


class ReminderStore:
    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, due_at TEXT NOT NULL,"
            " text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)"
        )
        self._db.commit()

    def add(self, due_at: datetime, text: str) -> int:
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO reminders (due_at, text) VALUES (?, ?)", (due_at.isoformat(), text)
            )
            return int(cur.lastrowid)

    def _query(self, where: str, args: tuple) -> list[Reminder]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, due_at, text FROM reminders"
                f" WHERE done = 0 AND {where} ORDER BY due_at",
                args,
            ).fetchall()
        return [Reminder(i, datetime.fromisoformat(d), t) for i, d, t in rows]

    def due(self, now: datetime) -> list[Reminder]:
        # Comparação por instante: todos os lembretes guardam o fuso.
        return [r for r in self._query("1 = 1", ()) if r.due_at <= now]

    def upcoming(self, now: datetime) -> list[Reminder]:
        return [r for r in self._query("1 = 1", ()) if r.due_at > now]

    def mark_done(self, reminder_id: int) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))


def make_reminder_tools(
    store: ReminderStore, tz: ZoneInfo, now: Callable[[], datetime] | None = None
) -> list[Tool]:
    now = now or (lambda: datetime.now(tz))

    async def remind_me(text: str, in_minutes: int | None = None, at: str = "") -> str:
        if not text.strip():
            return "ERRO: falta o texto do lembrete."
        current = now()
        try:
            if at:
                due = datetime.fromisoformat(at)
                due = due.replace(tzinfo=tz) if due.tzinfo is None else due.astimezone(tz)
            elif in_minutes is not None:
                due = current + timedelta(minutes=int(in_minutes))
            else:
                return "ERRO: diz quando (in_minutes ou at AAAA-MM-DDTHH:MM)."
        except ValueError:
            return "ERRO: hora inválida; usa AAAA-MM-DDTHH:MM."
        if due <= current:
            return "ERRO: essa hora já passou."
        store.add(due, text.strip())
        day = "hoje" if due.date() == current.date() else f"{due:%d/%m}"
        return f"Lembrete marcado para {day} às {due:%H:%M}: {text.strip()}."

    async def list_reminders() -> str:
        items = store.upcoming(now())
        if not items:
            return "Sem lembretes."
        return "\n".join(f"- {r.due_at.astimezone(tz):%d/%m %H:%M} {r.text}" for r in items)

    return [
        Tool(
            name="remind_me",
            description=(
                "Cria um lembrete: daqui a in_minutes minutos ou a uma hora "
                "(at, AAAA-MM-DDTHH:MM). "
                "A Friday avisa no Telegram e em voz se estiveres a falar com ela."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "in_minutes": {"type": "integer"},
                    "at": {"type": "string"},
                },
                "required": ["text"],
            },
            handler=remind_me,
        ),
        Tool(
            name="list_reminders",
            description="Lista os lembretes pendentes.",
            parameters={"type": "object", "properties": {}},
            handler=list_reminders,
        ),
    ]
