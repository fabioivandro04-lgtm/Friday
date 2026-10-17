"""`python -m friday` — arranca o Friday Core (ou liga contas: `connect google|microsoft`)."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn

from friday.agent.text_agent import OpenAIChatClient, TextAgent
from friday.channels.telegram import TelegramBot
from friday.channels.twilio import OneTimeTokens, TwilioCaller, TwilioGateway
from friday.config import Config, load_config
from friday.envfile import read_env_file
from friday.integrations.auth import connect_google, connect_microsoft
from friday.integrations.setup import (
    GOOGLE_CLIENT_SECRET,
    GOOGLE_TOKEN,
    MICROSOFT_CACHE,
    build_hub,
)
from friday.integrations.tools import make_integration_tools
from friday.llm.providers import select_endpoint
from friday.memory.store import Embedder, FastEmbedder, MemoryStore
from friday.memory.tools import make_memory_tools
from friday.proactive.briefing import Briefing
from friday.proactive.reminders import ReminderStore, make_reminder_tools
from friday.proactive.scheduler import Announcer, Notifier, Scheduler
from friday.server.app import create_app
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import Tool, ToolRegistry
from friday.tools.weather import make_weather_tool
from friday.voice.offline_stt import FileTranscriber
from friday.voice.processors import VoiceDeps

# A interface (app/dist, gerada por `npm run build`) é servida em / para o telemóvel.
APP_DIST = Path(__file__).resolve().parents[3] / "app" / "dist"


@dataclass
class Services:
    deps: VoiceDeps
    agent: TextAgent
    telegram: TelegramBot | None
    twilio: TwilioGateway | None
    background: list[Callable[[], Awaitable[None]]] = field(default_factory=list)


def _call_me_tool(caller: TwilioCaller) -> Tool:
    async def call_me(message: str = "") -> str:
        await caller.call(message or "Olá, é a Friday. Querias falar comigo?")
        return "A ligar-te agora."

    return Tool(
        name="call_me",
        description="Liga para o telemóvel do utilizador (só o número configurado).",
        parameters={"type": "object", "properties": {"message": {"type": "string"}}},
        handler=call_me,
    )


def build_services(cfg: Config, embedder: Embedder | None = None) -> Services:
    tz = ZoneInfo(cfg.integrations.timezone)
    now = lambda: datetime.now(tz)  # noqa: E731
    memory = MemoryStore(cfg.memory.db_path, embedder or FastEmbedder(), cfg.memory.min_similarity)
    reminders = ReminderStore(cfg.memory.db_path)
    hub = build_hub(cfg.integrations)
    weather = make_weather_tool(cfg.briefing.city)

    registry = ToolRegistry()
    tools = [weather, *make_memory_tools(memory), *make_reminder_tools(reminders, tz)]
    tools += make_integration_tools(hub, tz)
    from friday.tools.web_search import make_web_search_tool

    tools.append(make_web_search_tool())

    twilio = caller = None
    if cfg.twilio.enabled:
        tokens = OneTimeTokens()
        caller = TwilioCaller(cfg.twilio, tokens)
        tools.append(_call_me_tool(caller))
    for tool in tools:
        registry.register(tool)

    announcer = Announcer()
    deps = VoiceDeps(
        registry=registry,
        confirmations=ConfirmationManager(),
        memory=memory,
        hub=hub,
        announcer=announcer,
    )
    client = OpenAIChatClient(select_endpoint(cfg.llm))
    agent = TextAgent(cfg, registry, memory, client)

    if caller is not None:
        from friday.voice.pipeline import run_voice_session

        async def telephony(ws, start: dict, greeting: str) -> None:
            await run_voice_session(ws, cfg, deps, telephony=start, greeting=greeting)

        twilio = TwilioGateway(cfg.twilio, tokens, telephony)

    telegram = None
    background: list[Callable[[], Awaitable[None]]] = []
    if cfg.telegram.enabled and cfg.telegram.token:
        telegram = TelegramBot(
            cfg.telegram.token,
            cfg.telegram.allowed_chat_id,
            agent.reply,
            transcribe=FileTranscriber(cfg.stt.model, cfg.stt.device),
        )
        background.append(telegram.run)

    briefing = Briefing(hub, weather.handler, client, tz, now=now)
    notifier = Notifier(telegram=telegram, announcer=announcer)
    deliver = caller.call if (caller and cfg.briefing.channel == "call") else None
    scheduler = Scheduler(
        reminders, notifier, briefing, cfg.briefing, now=now, deliver_briefing=deliver
    )
    background.append(scheduler.run)
    return Services(deps, agent, telegram, twilio, background)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="friday", description="Friday Core")
    parser.add_argument("--config", type=Path, default=Path("friday.toml"))
    sub = parser.add_subparsers(dest="command")
    parser.set_defaults(command="serve")  # depois do add_subparsers, senão fica None
    sub.add_parser("serve", help="arranca o Core (padrão)")
    connect = sub.add_parser("connect", help="liga uma conta (Google ou Microsoft)")
    connect.add_argument("service", choices=["google", "microsoft"])
    return parser


def _connect(cfg: Config, service: str) -> None:
    secrets = Path(cfg.integrations.secrets_dir)
    if service == "google":
        client_secret = secrets / GOOGLE_CLIENT_SECRET
        if not client_secret.exists():
            raise SystemExit(
                f"Falta {client_secret}: descarrega-o da Google Cloud Console (ver README)."
            )
        connect_google(client_secret, secrets / GOOGLE_TOKEN)
    else:
        if not cfg.integrations.microsoft_client_id:
            raise SystemExit(
                "Falta [integrations] microsoft_client_id no friday.toml (ver README)."
            )
        connect_microsoft(cfg.integrations.microsoft_client_id, secrets / MICROSOFT_CACHE)
    print(f"Conta {service} ligada. Reinicia o Core para a Friday a usar.")


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO)
    # core/.env (chaves) ao lado do friday.toml; variáveis já definidas têm prioridade.
    env = {**read_env_file(args.config.parent / ".env"), **os.environ}
    cfg = load_config(args.config, env=env)
    if args.command == "connect":
        _connect(cfg, args.service)
        return
    from friday.voice.pipeline import run_voice_session

    services = build_services(cfg)

    async def voice_handler(websocket):
        await run_voice_session(websocket, cfg, services.deps)

    app = create_app(
        cfg,
        voice_handler=voice_handler,
        static_dir=APP_DIST,
        twilio=services.twilio,
        background=services.background,
    )
    # Sem access log: o token vai no URL do WebSocket e não deve ficar escrito.
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, access_log=False)


if __name__ == "__main__":
    main()
