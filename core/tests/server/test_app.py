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


def _twilio_app(cfg, tmp_path):
    from friday.channels.twilio import OneTimeTokens, TwilioGateway
    from friday.config import TwilioConfig

    tw = TwilioConfig(
        enabled=True, account_sid="AC1", public_url="https://pc.tail1.ts.net", auth_token="secret"
    )
    tokens = OneTimeTokens()
    calls = []

    async def handler(ws, start, greeting):
        calls.append((start, greeting))
        await ws.close()

    gateway = TwilioGateway(tw, tokens, handler)
    return create_app(cfg, twilio=gateway), tokens, calls


def _sign(url, params, token="secret"):
    import base64
    import hashlib
    import hmac

    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


def test_twilio_voice_webhook_requires_signature(cfg, tmp_path):
    app, tokens, _ = _twilio_app(cfg, tmp_path)
    t = tokens.issue({"greeting": "Olá"})
    params = {"CallSid": "CA9", "From": "+351210000000"}
    url = f"https://pc.tail1.ts.net/twilio/voice?t={t}"
    client = _client(app)
    bad = client.post(
        f"/twilio/voice?t={t}",
        data=params,
        headers={"X-Twilio-Signature": "nope", "host": "pc.tail1.ts.net"},
    )
    assert bad.status_code == 403
    ok = client.post(
        f"/twilio/voice?t={t}",
        data=params,
        headers={"X-Twilio-Signature": _sign(url, params), "host": "pc.tail1.ts.net"},
    )
    assert ok.status_code == 200 and "wss://pc.tail1.ts.net/twilio/ws?t=" in ok.text


def test_twilio_ws_consumes_token_once(cfg, tmp_path):
    import json

    app, tokens, calls = _twilio_app(cfg, tmp_path)
    t = tokens.issue({"greeting": "Olá"})
    client = _client(app)
    with client.websocket_connect(f"/twilio/ws?t={t}") as ws:
        ws.send_text(json.dumps({"event": "connected"}))
        ws.send_text(
            json.dumps({"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA9"}})
        )
    assert calls == [({"streamSid": "MZ1", "callSid": "CA9"}, "Olá")]
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/twilio/ws?t={t}"):
            pass
    assert e.value.code == 4401
