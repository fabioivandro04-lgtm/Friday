"""Cliente de teste: envia um .wav ao /ws como o browser faria e recolhe os eventos."""

from __future__ import annotations

import time
import wave
from pathlib import Path
from typing import Any

from pipecat.frames.frames import AudioRawFrame, OutputAudioRawFrame
from pipecat.serializers.protobuf import ProtobufFrameSerializer

CHUNK_MS = 20


def read_wav(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        return w.readframes(w.getnframes())


async def encode_audio(serializer: ProtobufFrameSerializer, pcm: bytes) -> list[bytes]:
    step = 16000 * 2 * CHUNK_MS // 1000
    return [
        await serializer.serialize(
            OutputAudioRawFrame(audio=pcm[i : i + step], sample_rate=16000, num_channels=1)
        )
        for i in range(0, len(pcm), step)
    ]


def rtvi_event(frame: Any) -> dict | None:
    message = getattr(frame, "message", None)
    if isinstance(message, dict) and message.get("type") == "server-message":
        return message.get("data")
    return None


def is_audio(frame: Any) -> bool:
    return isinstance(frame, OutputAudioRawFrame | AudioRawFrame)


def now_ms() -> float:
    return time.monotonic() * 1000
