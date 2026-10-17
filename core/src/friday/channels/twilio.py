"""Chamadas telefónicas pela Twilio: a Friday liga-te (resumo, avisos) e conversa por voz.

A Twilio pede o TwiML em /twilio/voice (assinatura validada) e liga o áudio a
/twilio/ws (token de uso único). Só se liga para o número configurado.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any
from xml.sax.saxutils import quoteattr

import httpx

from friday.config import TwilioConfig

API = "https://api.twilio.com/2010-04-01"


def _signature(url: str, params: dict[str, str], auth_token: str) -> str:
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def validate_signature(url: str, params: dict[str, str], signature: str, auth_token: str) -> bool:
    if not signature or not auth_token:
        return False
    return hmac.compare_digest(_signature(url, params, auth_token), signature)


def twiml_stream(ws_url: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Connect><Stream url={quoteattr(ws_url)} /></Connect></Response>"
    )


class OneTimeTokens:
    """Tokens curtos que ligam o pedido da Twilio à chamada que a Friday fez."""

    def __init__(self, ttl_s: float = 300.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._clock = ttl_s, clock
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}

    def issue(self, data: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(24)
        self._items[token] = (self._clock() + self._ttl, data)
        return token

    def peek(self, token: str) -> dict[str, Any] | None:
        item = self._items.get(token)
        if item is None or item[0] < self._clock():
            self._items.pop(token, None)
            return None
        return item[1]

    def consume(self, token: str) -> dict[str, Any] | None:
        data = self.peek(token)
        self._items.pop(token, None)
        return data


class TwilioCaller:
    def __init__(self, cfg: TwilioConfig, tokens: OneTimeTokens) -> None:
        self._cfg, self._tokens = cfg, tokens

    async def call(self, greeting: str) -> str:
        cfg = self._cfg
        for key in ("account_sid", "auth_token", "from_number", "to_number", "public_url"):
            if not getattr(cfg, key):
                raise ValueError(f"Twilio: falta {key} (friday.toml / TWILIO_AUTH_TOKEN no .env)")
        token = self._tokens.issue({"greeting": greeting})
        form = {
            "To": cfg.to_number,
            "From": cfg.from_number,
            "Url": f"{cfg.public_url.rstrip('/')}/twilio/voice?t={token}",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{API}/Accounts/{cfg.account_sid}/Calls.json",
                data=form,
                auth=(cfg.account_sid, cfg.auth_token),
            )
        response.raise_for_status()
        return response.json()["sid"]


TelephonyHandler = Callable[[Any, dict[str, Any], str], Awaitable[None]]


class TwilioGateway:
    """O que o servidor precisa para atender os pedidos da Twilio."""

    def __init__(self, cfg: TwilioConfig, tokens: OneTimeTokens, handler: TelephonyHandler) -> None:
        self.cfg, self.tokens, self.handler = cfg, tokens, handler

    def ws_url(self, token: str) -> str:
        base = self.cfg.public_url.rstrip("/").replace("https://", "wss://", 1)
        return f"{base}/twilio/ws?t={token}"
