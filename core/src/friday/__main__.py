"""`python -m friday` — arranca o Friday Core."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from friday.config import load_config
from friday.server.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="friday")
    parser.add_argument("--config", type=Path, default=Path("friday.toml"))
    args = parser.parse_args()
    cfg = load_config(args.config)
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port)


if __name__ == "__main__":
    main()
