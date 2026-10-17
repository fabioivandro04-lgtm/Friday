"""Teste de ponta a ponta: precisa da GPU, do Ollama com qwen3:8b e de friday.toml.

Corre no PC alvo com:  uv run pytest tests/voice -m gpu -v
"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pipecat.serializers.protobuf import ProtobufFrameSerializer

from friday.__main__ import build_services
from friday.config import load_config
from friday.server.app import create_app
from friday.voice.pipeline import run_voice_session

from .gpu_client import encode_audio, is_audio, read_wav, rtvi_event

FIXTURE = Path(__file__).parent / "fixtures" / "ola_friday_pt.wav"
CONFIG = Path(__file__).parents[2] / "friday.toml"


@pytest.mark.gpu
def test_spoken_question_gets_transcript_and_audio():
    cfg = load_config(CONFIG)
    deps = build_services(cfg).deps

    async def handler(ws):
        await run_voice_session(ws, cfg, deps)

    app = create_app(cfg, voice_handler=handler)
    client = TestClient(app, client=("127.0.0.1", 50000))
    token = client.get("/pair").json()["token"]
    serializer = ProtobufFrameSerializer()
    chunks = asyncio.run(encode_audio(serializer, read_wav(FIXTURE)))

    user_texts, got_audio = [], False
    with client.websocket_connect(f"/ws?token={token}") as ws:
        # Como a app: só falar depois de o pipeline estar pronto.
        while not (
            (e := rtvi_event(asyncio.run(serializer.deserialize(ws.receive_bytes()))))
            and e["type"] == "state"
        ):
            pass
        for chunk in chunks:
            ws.send_bytes(chunk)
        for _ in range(2000):
            frame = asyncio.run(serializer.deserialize(ws.receive_bytes()))
            event = rtvi_event(frame)
            if event and event["type"] == "transcript" and event["data"]["role"] == "user":
                user_texts.append(event["data"]["text"].lower())
            if is_audio(frame):
                got_audio = True
            if user_texts and got_audio:
                break

    assert any("horas" in t for t in user_texts)
    assert got_audio
