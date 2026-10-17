"""Agente de texto (Telegram, resumo diário): o mesmo cérebro, por escrito.

Reutiliza as ferramentas, a memória e as confirmações da voz. Cada conversa
(ex.: um chat do Telegram) tem o seu histórico e as suas ações pendentes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from friday.config import Config
from friday.llm.providers import LlmEndpoint
from friday.persona import system_prompt
from friday.tools.confirm import ConfirmationManager, PendingAction, is_hedge, parse_confirmation
from friday.tools.registry import ToolRegistry, execute
from friday.voice.language import Lang

logger = logging.getLogger("friday.agent")

_MAX_TOOL_ROUNDS = 5
_MAX_HISTORY = 30
_TEXT_MODE = {
    "pt": (
        "\nCanal: estás a responder por mensagem escrita (Telegram). Podes usar até 6 frases "
        "e listas curtas, sem markdown pesado. Responde na língua da mensagem (PT-PT ou inglês).\n"
    ),
    "en": (
        "\nChannel: you are replying by written message (Telegram). Up to 6 sentences and "
        "short lists are fine, no heavy markdown.\n"
    ),
}
_SAY = {
    "pt": {
        "cancelled": "Cancelado.",
        "ask_again": "Confirmas? Responde sim ou não.",
        "done": "Feito",
        "llm_down": "O modelo não está a responder. Tenta daqui a pouco.",
        "stuck": "Não consegui terminar isso. Podes reformular?",
    },
    "en": {
        "cancelled": "Cancelled.",
        "ask_again": "Do you confirm? Reply yes or no.",
        "done": "Done",
        "llm_down": "The model isn't responding. Try again shortly.",
        "stuck": "I couldn't finish that. Could you rephrase?",
    },
}
_EN_WORDS = {
    "the",
    "is",
    "what",
    "how",
    "you",
    "are",
    "can",
    "please",
    "my",
    "and",
    "do",
    "tomorrow",
    "today",
    "weather",
    "send",
    "email",
    "remind",
    "me",
}
_PT_WORDS = {
    "o",
    "a",
    "que",
    "é",
    "como",
    "está",
    "estás",
    "podes",
    "meu",
    "minha",
    "e",
    "amanhã",
    "hoje",
    "tempo",
    "envia",
    "lembra",
    "não",
    "sim",
    "de",
    "para",
}


class ChatClient(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


class OpenAIChatClient:
    """Cliente real: qualquer endpoint compatível com a OpenAI (Ollama, OpenRouter)."""

    def __init__(self, endpoint: LlmEndpoint) -> None:
        from openai import AsyncOpenAI

        self._endpoint = endpoint
        self._client = AsyncOpenAI(base_url=endpoint.base_url, api_key=endpoint.api_key)

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        response = await self._client.chat.completions.create(
            model=self._endpoint.model,
            messages=messages,
            tools=tools or None,
            extra_body=self._endpoint.extra_body or None,
        )
        msg = response.choices[0].message
        calls = []
        for c in msg.tool_calls or []:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": c.id, "name": c.function.name, "arguments": args})
        return {"content": msg.content, "tool_calls": calls}


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def guess_language(text: str, previous: Lang) -> Lang:
    words = set(re.findall(r"[a-zà-ú]+", text.lower()))
    en, pt = len(words & _EN_WORDS), len(words & _PT_WORDS)
    if en >= 2 and en > pt:
        return "en"
    if pt >= 2 and pt > en:
        return "pt"
    return previous


class TextAgent:
    def __init__(
        self, cfg: Config, registry: ToolRegistry, memory: Any, client: ChatClient
    ) -> None:
        self._cfg = cfg
        self._registry = registry
        self._memory = memory
        self._client = client
        self._tz = ZoneInfo(cfg.integrations.timezone)
        self._history: dict[str, list[dict]] = defaultdict(list)
        self._confirmations: dict[str, ConfirmationManager] = defaultdict(ConfirmationManager)
        self._asked_again: dict[str, str] = {}
        self._lang: dict[str, Lang] = defaultdict(lambda: "pt")
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def pending(self, conversation: str) -> PendingAction | None:
        return self._confirmations[conversation].pending()

    async def reply(self, conversation: str, text: str) -> str:
        async with self._locks[conversation]:
            lang = guess_language(text, self._lang[conversation])
            self._lang[conversation] = lang
            pending = self.pending(conversation)
            if pending is not None:
                answer = await self._answer_pending(conversation, pending, text, lang)
                if answer is not None:
                    return answer
            return await self._converse(conversation, text, lang)

    async def _answer_pending(
        self, conversation: str, pending: PendingAction, text: str, lang: Lang
    ) -> str | None:
        conf = self._confirmations[conversation]
        if parse_confirmation(text) == "unclear":
            if is_hedge(text) and self._asked_again.get(conversation) != pending.id:
                self._asked_again[conversation] = pending.id
                return _SAY[lang]["ask_again"]
            conf.cancel()  # outra conversa: a ação cai e a mensagem é respondida
            return None
        if conf.resolve(text) == "rejected":
            return _SAY[lang]["cancelled"]
        try:
            result = await self._registry.get(pending.tool).handler(**pending.args)
        except Exception as e:  # noqa: BLE001
            return f"ERRO: {e}"
        self._remember_exchange(conversation, "user", text)
        self._remember_exchange(conversation, "assistant", f"{_SAY[lang]['done']}: {result}")
        return f"{_SAY[lang]['done']}: {result}"

    def _remember_exchange(self, conversation: str, role: str, content: str) -> None:
        history = self._history[conversation]
        history.append({"role": role, "content": content})
        del history[:-_MAX_HISTORY]

    async def _converse(self, conversation: str, text: str, lang: Lang) -> str:
        memory = await asyncio.to_thread(self._memory.context_for, text)
        system = system_prompt(lang, memory, now=datetime.now(self._tz)) + _TEXT_MODE[lang]
        self._remember_exchange(conversation, "user", text)
        await asyncio.to_thread(self._memory.log_turn, "user", text)
        messages = [{"role": "system", "content": system}, *self._history[conversation]]
        tools = self._registry.schemas()
        for _ in range(_MAX_TOOL_ROUNDS):
            try:
                answer = await self._client.complete(messages, tools)
            except Exception as e:  # noqa: BLE001
                logger.warning("LLM falhou: %s", e)
                return _SAY[lang]["llm_down"]
            calls = answer.get("tool_calls") or []
            if not calls:
                content = strip_thinking(answer.get("content") or "")
                self._remember_exchange(conversation, "assistant", content)
                await asyncio.to_thread(self._memory.log_turn, "assistant", content)
                return content
            messages.append(
                {
                    "role": "assistant",
                    "content": answer.get("content") or "",
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": json.dumps(c["arguments"]),
                            },
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                result = await execute(
                    self._registry, self._confirmations[conversation], c["name"], c["arguments"]
                )
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
        return _SAY[lang]["stuck"]
