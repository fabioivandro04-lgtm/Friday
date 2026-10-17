"""Servidor HTTP/WebSocket do Friday Core."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from friday.channels.twilio import TwilioGateway, twiml_stream, validate_signature
from friday.config import Config
from friday.server.auth import (
    TokenStore,
    is_allowed_host,
    is_allowed_ip,
    is_allowed_origin,
    is_localhost,
)

VoiceHandler = Callable[[WebSocket], Awaitable[None]]
WS_UNAUTHORISED = 4401
# Cabeçalhos que um proxy (ex.: `tailscale serve`) acrescenta: o pedido não é deste PC.
_PROXY_HEADERS = ("x-forwarded-for", "tailscale-user-login", "forwarded")


def _from_funnel(conn: Request | WebSocket) -> bool:
    return "tailscale-funnel-request" in conn.headers


def _client_ip(conn: Request | WebSocket) -> str:
    return conn.client.host if conn.client else ""


def create_app(
    cfg: Config,
    voice_handler: VoiceHandler | None = None,
    static_dir: Path | None = None,
    twilio: TwilioGateway | None = None,
    background: list[Callable[[], Awaitable[None]]] | None = None,
) -> FastAPI:
    tokens = TokenStore(Path(cfg.memory.db_path).with_suffix(".token"), fixed=cfg.server.token)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Telegram, agendador, …: correm enquanto o Core estiver ligado.
        tasks = [asyncio.create_task(job()) for job in background or []]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()

    app = FastAPI(title="Friday Core", lifespan=lifespan)

    @app.middleware("http")
    async def only_allowed_ips(request: Request, call_next):
        if not is_allowed_ip(_client_ip(request)):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        if _from_funnel(request) and not request.url.path.startswith("/twilio/"):
            # Pela internet (Tailscale Funnel) só a Twilio tem caminho aberto.
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        if not is_allowed_host(request.headers.get("host", "")):
            return JSONResponse({"detail": "bad host"}, status_code=400)
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/pair")
    async def pair(request: Request):
        # O token só é mostrado no próprio PC; o utilizador cola-o no telemóvel.
        proxied = any(h in request.headers for h in _PROXY_HEADERS)
        if proxied or not is_localhost(_client_ip(request)):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        return {"token": tokens.get_or_create()}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, token: str = "") -> None:
        allowed = (
            not _from_funnel(websocket)
            and is_allowed_ip(_client_ip(websocket))
            and is_allowed_host(websocket.headers.get("host", ""))
            and is_allowed_origin(websocket.headers.get("origin"))
            and token
            and tokens.check(token)
        )
        if not allowed:
            await websocket.close(code=WS_UNAUTHORISED)
            return
        if voice_handler is None:
            await websocket.close()
            return
        await voice_handler(websocket)

    if twilio is not None:
        _add_twilio_routes(app, twilio)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="pwa")

    return app


def _add_twilio_routes(app: FastAPI, twilio: TwilioGateway) -> None:
    @app.post("/twilio/voice")
    async def twilio_voice(request: Request, t: str = ""):
        form = {k: str(v) for k, v in (await request.form()).items()}
        # A assinatura cobre o URL público exato que a Twilio chamou.
        url = f"{twilio.cfg.public_url.rstrip('/')}{request.url.path}"
        if request.url.query:
            url += f"?{request.url.query}"
        signature = request.headers.get("x-twilio-signature", "")
        if not validate_signature(url, form, signature, twilio.cfg.auth_token or ""):
            return JSONResponse({"detail": "bad signature"}, status_code=403)
        if twilio.tokens.peek(t) is None:
            return JSONResponse({"detail": "unknown call"}, status_code=403)
        return Response(twiml_stream(twilio.ws_url(t)), media_type="application/xml")

    @app.websocket("/twilio/ws/{t}")
    async def twilio_ws(websocket: WebSocket, t: str) -> None:
        data = twilio.tokens.consume(t)
        if data is None:
            await websocket.close(code=WS_UNAUTHORISED)
            return
        await websocket.accept()
        start: dict = {}
        while not start:  # "connected" e depois "start" com o streamSid
            message = json.loads(await websocket.receive_text())
            if message.get("event") == "start":
                start = message.get("start", {})
        await twilio.handler(websocket, start, data.get("greeting", ""))
