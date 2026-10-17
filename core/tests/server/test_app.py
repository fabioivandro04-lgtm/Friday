import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from friday.config import Config, MemoryConfig, TtsConfig
from friday.server.app import create_app

LOCAL = ("127.0.0.1", 50000)
TAILSCALE = ("100.101.5.9", 50000)
LAN = ("192.168.1.20", 50000)


@pytest.fixture
def cfg(tmp_path):
    return Config(tts=TtsConfig("pt", "en"), memory=MemoryConfig(db_path=str(tmp_path / "f.db")))


def _client(app, addr=LOCAL):
    return TestClient(app, client=addr)


def test_health_ok(cfg):
    assert _client(create_app(cfg)).get("/health").json() == {"status": "ok"}


def test_lan_ip_forbidden(cfg):
    assert _client(create_app(cfg), LAN).get("/health").status_code == 403


def test_pair_only_from_localhost(cfg):
    app = create_app(cfg)
    assert _client(app, TAILSCALE).get("/pair").status_code == 403
    token = _client(app).get("/pair").json()["token"]
    assert len(token) >= 32


def test_ws_rejects_bad_token(cfg):
    with pytest.raises(WebSocketDisconnect) as e:
        with _client(create_app(cfg)).websocket_connect("/ws?token=wrong"):
            pass
    assert e.value.code == 4401


def test_ws_rejects_lan_ip_even_with_token(cfg):
    app = create_app(cfg)
    token = _client(app).get("/pair").json()["token"]
    with pytest.raises(WebSocketDisconnect) as e:
        with _client(app, LAN).websocket_connect(f"/ws?token={token}"):
            pass
    assert e.value.code == 4401


def test_ws_with_token_calls_handler(cfg):
    calls = []

    async def handler(ws):
        calls.append(ws)
        await ws.accept()
        await ws.send_json({"hello": "friday"})
        await ws.close()

    app = create_app(cfg, voice_handler=handler)
    token = _client(app).get("/pair").json()["token"]
    with _client(app, TAILSCALE).websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json() == {"hello": "friday"}
    assert len(calls) == 1


def test_serves_static_pwa(cfg, tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<h1>Friday</h1>")
    resp = _client(create_app(cfg, static_dir=static)).get("/")
    assert "Friday" in resp.text


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Tailscale-User-Login"])
def test_pair_refused_through_a_proxy(cfg, header):
    # Via `tailscale serve` o pedido chega de 127.0.0.1, mas vem de outro dispositivo.
    resp = _client(create_app(cfg)).get("/pair", headers={header: "100.101.5.9"})
    assert resp.status_code == 403


@pytest.mark.parametrize("host", ["evil.example.com", "evil.example.com:8765"])
def test_unknown_host_header_rejected(cfg, host):
    # Defesa contra DNS rebinding: o /pair não pode ser lido por outro site.
    assert _client(create_app(cfg)).get("/pair", headers={"host": host}).status_code == 400


@pytest.mark.parametrize(
    "host", ["127.0.0.1:8765", "localhost:8765", "pc.tail1234.ts.net", "100.101.5.9:8765"]
)
def test_known_hosts_allowed(cfg, host):
    assert _client(create_app(cfg)).get("/health", headers={"host": host}).status_code == 200


def test_ws_rejects_foreign_origin(cfg):
    app = create_app(cfg, voice_handler=lambda ws: ws.accept())
    token = _client(app).get("/pair").json()["token"]
    with pytest.raises(WebSocketDisconnect) as e:
        with _client(app).websocket_connect(
            f"/ws?token={token}", headers={"origin": "https://evil.example.com"}
        ):
            pass
    assert e.value.code == 4401


@pytest.mark.parametrize(
    "origin", ["tauri://localhost", "http://tauri.localhost", "http://127.0.0.1:8765"]
)
def test_ws_accepts_app_origins(cfg, origin):
    async def handler(ws):
        await ws.accept()
        await ws.close()

    app = create_app(cfg, voice_handler=handler)
    token = _client(app).get("/pair").json()["token"]
    with _client(app).websocket_connect(f"/ws?token={token}", headers={"origin": origin}):
        pass
