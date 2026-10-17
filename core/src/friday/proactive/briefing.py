"""Resumo da manhã: agenda + emails por ler + tempo, escrito pela Friday."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from friday.agent.text_agent import ChatClient, strip_thinking
from friday.integrations.hub import IntegrationHub
from friday.persona import system_prompt

logger = logging.getLogger("friday.briefing")


class Briefing:
    def __init__(
        self,
        hub: IntegrationHub,
        weather: Callable[[], Awaitable[str]],
        client: ChatClient,
        tz: ZoneInfo,
        now: Callable[[], datetime],
    ) -> None:
        self._hub, self._weather, self._client, self._tz, self._now = hub, weather, client, tz, now

    async def _facts(self) -> str:
        now = self._now()
        events = await self._hub.agenda(now.date())
        mails = await self._hub.inbox(5)
        agenda = (
            "\n".join(
                f"- {'dia todo' if e.all_day else f'{e.start:%H:%M}'} {e.title}" for e in events
            )
            or "- nada marcado"
        )
        inbox = "\n".join(f"- {m.sender}: {m.subject}" for m in mails) or "- sem emails por ler"
        weather = await self._weather()
        return f"Agenda de hoje:\n{agenda}\n\nEmails por ler:\n{inbox}\n\nTempo:\n{weather}"

    async def build(self) -> str:
        facts = await self._facts()
        messages = [
            {"role": "system", "content": system_prompt("pt", now=self._now())},
            {
                "role": "user",
                "content": (
                    "Escreve o meu resumo da manhã em português de Portugal, no máximo 6 frases, "
                    "começando por 'Bom dia'. Destaca o primeiro compromisso e o que é urgente. "
                    "Usa só estes dados:\n\n" + facts
                ),
            },
        ]
        try:
            answer = await self._client.complete(messages, [])
            text = strip_thinking(answer.get("content") or "")
            if text:
                return text
        except Exception as e:  # noqa: BLE001
            logger.warning("Resumo: LLM falhou (%s); a enviar os dados em bruto.", e)
        return f"Bom dia!\n\n{facts}"
