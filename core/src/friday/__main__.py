"""`python -m friday` — arranca o Friday Core."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from friday.config import Config, load_config
from friday.memory.store import FastEmbedder, MemoryStore
from friday.memory.tools import make_memory_tools
from friday.server.app import create_app
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import ToolRegistry
from friday.tools.web_search import make_web_search_tool


def build_deps(cfg: Config):
    from friday.voice.pipeline import VoiceDeps

    memory = MemoryStore(cfg.memory.db_path, FastEmbedder(), cfg.memory.min_similarity)
    registry = ToolRegistry()
    for tool in [make_web_search_tool(), *make_memory_tools(memory)]:
        registry.register(tool)
    return VoiceDeps(registry=registry, confirmations=ConfirmationManager(), memory=memory)


def main() -> None:
    parser = argparse.ArgumentParser(prog="friday")
    parser.add_argument("--config", type=Path, default=Path("friday.toml"))
    args = parser.parse_args()
    cfg = load_config(args.config)
    from friday.voice.pipeline import run_voice_session

    deps = build_deps(cfg)

    async def voice_handler(websocket):
        await run_voice_session(websocket, cfg, deps)

    app = create_app(cfg, voice_handler=voice_handler)
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port)


if __name__ == "__main__":
    main()
