"""Servidor HTTP/WebSocket do Friday Core."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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


def _client_ip(conn: Request | WebSocket) -> str:
    return conn.client.host if conn.client else ""


def create_app(
    cfg: Config, voice_handler: VoiceHandler | None = None, static_dir: Path | None = None
) -> FastAPI:
    tokens = TokenStore(Path(cfg.memory.db_path).with_suffix(".token"), fixed=cfg.server.token)
    app = FastAPI(title="Friday Core")

    @app.middleware("http")
    async def only_allowed_ips(request: Request, call_next):
        if not is_allowed_ip(_client_ip(request)):
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
            is_allowed_ip(_client_ip(websocket))
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

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="pwa")

    return app
