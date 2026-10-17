"""`python -m friday` — arranca o Friday Core."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn

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
from friday.memory.store import FastEmbedder, MemoryStore
from friday.memory.tools import make_memory_tools
from friday.server.app import create_app
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import ToolRegistry
from friday.tools.web_search import make_web_search_tool

# A interface (app/dist, gerada por `npm run build`) é servida em / para o telemóvel.
APP_DIST = Path(__file__).resolve().parents[3] / "app" / "dist"


def build_deps(cfg: Config):
    from friday.voice.pipeline import VoiceDeps

    memory = MemoryStore(cfg.memory.db_path, FastEmbedder(), cfg.memory.min_similarity)
    hub = build_hub(cfg.integrations)
    registry = ToolRegistry()
    tools = [make_web_search_tool(), *make_memory_tools(memory)]
    tools += make_integration_tools(hub, ZoneInfo(cfg.integrations.timezone))
    for tool in tools:
        registry.register(tool)
    return VoiceDeps(registry=registry, confirmations=ConfirmationManager(), memory=memory, hub=hub)


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

    deps = build_deps(cfg)

    async def voice_handler(websocket):
        await run_voice_session(websocket, cfg, deps)

    app = create_app(cfg, voice_handler=voice_handler, static_dir=APP_DIST)
    # Sem access log: o token vai no URL do WebSocket e não deve ficar escrito.
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, access_log=False)


if __name__ == "__main__":
    main()
