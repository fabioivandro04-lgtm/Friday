from pathlib import Path

from friday.__main__ import build_parser


def test_default_is_serve():
    args = build_parser().parse_args([])
    assert args.command == "serve" and args.config == Path("friday.toml")


def test_connect_google_and_microsoft():
    p = build_parser()
    assert p.parse_args(["connect", "google"]).service == "google"
    assert p.parse_args(["--config", "x.toml", "connect", "microsoft"]).service == "microsoft"
