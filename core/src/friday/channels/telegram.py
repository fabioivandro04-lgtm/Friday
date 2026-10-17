"""Bot do Telegram: falar com a Friday por mensagem e receber avisos.

Usa long polling (não precisa de servidor público) e só responde ao chat
configurado em [telegram] allowed_chat_id.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger("friday.telegram")

Handler = Callable[[str, str], Awaitable[str]]
Transcribe = Callable[[bytes], Awaitable[str]]
_MAX_LEN = 4000
_POLL_TIMEOUT_S = 30


class TelegramBot:
    def __init__(
        self,
        token: str,
        allowed_chat_id: int | None,
        handler: Handler,
        transcribe: Transcribe | None = None,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        self._api = f"{base_url}/bot{token}"
        self._files = f"{base_url}/file/bot{token}"
        self._allowed = allowed_chat_id
        self._handler = handler
        self._transcribe = transcribe
        self._offset = 0

    async def _call(self, method: str, http: str = "post", **payload) -> dict:
        timeout = httpx.Timeout(_POLL_TIMEOUT_S + 10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if http == "get":
                response = await client.get(f"{self._api}/{method}", params=payload)
            else:
                response = await client.post(f"{self._api}/{method}", json=payload)
        response.raise_for_status()
        return response.json()

    async def send(self, chat_id: int, text: str) -> None:
        text = text.strip() or "…"
        for i in range(0, len(text), _MAX_LEN):
            await self._call("sendMessage", chat_id=chat_id, text=text[i : i + _MAX_LEN])

    async def notify(self, text: str) -> None:
        """Aviso proativo (lembrete, resumo diário) para o dono do bot."""
        if self._allowed is None:
            logger.warning("Telegram sem allowed_chat_id: aviso não enviado.")
            return
        await self.send(self._allowed, text)

    async def _download(self, file_id: str) -> bytes:
        info = await self._call("getFile", http="get", file_id=file_id)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self._files}/{info['result']['file_path']}")
        response.raise_for_status()
        return response.content

    async def _handle(self, message: dict) -> None:
        chat_id = message.get("chat", {}).get("id")
        if self._allowed is None:
            # Configuração inicial: só diz o id, não processa nada.
            await self.send(
                chat_id,
                f"O teu chat id é {chat_id}. Põe-no em [telegram] allowed_chat_id no friday.toml.",
            )
            return
        if chat_id != self._allowed:
            logger.warning("Mensagem ignorada de um chat não autorizado: %s", chat_id)
            return
        text = message.get("text", "")
        prefix = ""
        if not text and "voice" in message:
            if self._transcribe is None:
                await self.send(chat_id, "As notas de voz não estão disponíveis.")
                return
            text = await self._transcribe(await self._download(message["voice"]["file_id"]))
            prefix = f"«{text}»\n\n"
        if not text.strip():
            return
        await self._call("sendChatAction", chat_id=chat_id, action="typing")
        try:
            answer = await self._handler(f"telegram:{chat_id}", text)
        except Exception as e:  # noqa: BLE001
            logger.exception("Erro a responder no Telegram")
            answer = f"Algo correu mal: {e}"
        await self.send(chat_id, prefix + answer)

    async def poll_once(self) -> None:
        data = await self._call(
            "getUpdates", http="get", offset=self._offset, timeout=_POLL_TIMEOUT_S
        )
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            if "message" in update:
                await self._handle(update["message"])

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                await self.poll_once()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — sem rede: tenta outra vez mais tarde
                logger.warning("Telegram: %s (nova tentativa em %.0fs)", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)
