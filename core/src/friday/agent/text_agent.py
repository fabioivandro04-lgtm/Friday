"""Agente de texto (Telegram, resumo diário): o mesmo cérebro, por escrito.

Reutiliza as ferramentas, a memória e as confirmações da voz. Cada conversa
(ex.: um chat do Telegram) tem o seu histórico e as suas ações pendentes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
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
_MAX_EXCHANGES = 12  # trocas completas (pedido, ferramentas, resposta) guardadas por conversa
# Por mensagem as pessoas demoram a responder: o pedido de confirmação dura 15 minutos.
_TEXT_CONFIRM_TTL_S = 15 * 60
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
        "confirm": "Confirmas? Responde sim ou não.",
        "expired": "Esse pedido expirou e não foi feito. Pede outra vez, por favor.",
    },
    "en": {
        "cancelled": "Cancelled.",
        "ask_again": "Do you confirm? Reply yes or no.",
        "done": "Done",
        "llm_down": "The model isn't responding. Try again shortly.",
        "stuck": "I couldn't finish that. Could you rephrase?",
        "confirm": "Do you confirm? Reply yes or no.",
        "expired": "That request expired and wasn't done. Please ask again.",
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
        self._history: dict[str, list[list[dict]]] = defaultdict(list)
        self._clock = time.monotonic
        self._confirmations: dict[str, ConfirmationManager] = {}
        self._asked_again: dict[str, str] = {}
        self._lang: dict[str, Lang] = defaultdict(lambda: "pt")
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _conf(self, conversation: str) -> ConfirmationManager:
        if conversation not in self._confirmations:
            self._confirmations[conversation] = ConfirmationManager(
                ttl_s=_TEXT_CONFIRM_TTL_S, clock=lambda: self._clock()
            )
        return self._confirmations[conversation]

    def pending(self, conversation: str) -> PendingAction | None:
        return self._conf(conversation).pending()

    async def reply(self, conversation: str, text: str) -> str:
        async with self._locks[conversation]:
            lang = guess_language(text, self._lang[conversation])
            self._lang[conversation] = lang
            pending = self.pending(conversation)
            if pending is None and self._conf(conversation).take_expired():
                if parse_confirmation(text) == "confirmed":
                    return _SAY[lang]["expired"]  # um "sim" tardio não vai para o LLM
            if pending is not None:
                answer = await self._answer_pending(conversation, pending, text, lang)
                if answer is not None:
                    return answer
            return await self._converse(conversation, text, lang)

    async def _answer_pending(
        self, conversation: str, pending: PendingAction, text: str, lang: Lang
    ) -> str | None:
        conf = self._conf(conversation)
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
        done = f"{_SAY[lang]['done']}: {result}"
        self._remember(
            [{"role": "user", "content": text}, {"role": "assistant", "content": done}],
            conversation,
        )
        return done

    def _remember(self, exchange: list[dict], conversation: str) -> None:
        # Trocas inteiras: uma mensagem "tool" nunca fica sem a chamada que a pediu.
        history = self._history[conversation]
        history.append(exchange)
        del history[:-_MAX_EXCHANGES]

    async def _converse(self, conversation: str, text: str, lang: Lang) -> str:
        memory = await asyncio.to_thread(self._memory.context_for, text)
        system = system_prompt(lang, memory, now=datetime.now(self._tz)) + _TEXT_MODE[lang]
        await asyncio.to_thread(self._memory.log_turn, "user", text)
        exchange: list[dict] = [{"role": "user", "content": text}]
        past = [m for ex in self._history[conversation] for m in ex]
        tools = self._registry.schemas()
        conf = self._conf(conversation)
        for _ in range(_MAX_TOOL_ROUNDS):
            try:
                answer = await self._client.complete(
                    [{"role": "system", "content": system}, *past, *exchange], tools
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("LLM falhou: %s", e)
                return _SAY[lang]["llm_down"]
            calls = answer.get("tool_calls") or []
            if not calls:
                content = strip_thinking(answer.get("content") or "")
                exchange.append({"role": "assistant", "content": content})
                self._remember(exchange, conversation)
                await asyncio.to_thread(self._memory.log_turn, "assistant", content)
                pending = conf.pending()
                if pending is not None:
                    # O que se confirma vem do código, não das palavras do LLM
                    # (que podem ter sido manipuladas por um email ou página web).
                    content = f"{content}\n\n➜ {pending.summary}. {_SAY[lang]['confirm']}".strip()
                return content
            exchange.append(
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
                result = await execute(self._registry, conf, c["name"], c["arguments"])
                exchange.append({"role": "tool", "tool_call_id": c["id"], "content": result})
        return _SAY[lang]["stuck"]
