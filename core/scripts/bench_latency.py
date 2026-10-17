"""Mede a latência da Friday com áudios gravados (16 kHz, mono, .wav).

Com o Core a correr (`uv run python -m friday`):
    uv run python -m scripts.bench_latency --audio-dir recordings --runs 5

Para cada áudio, envia-o em tempo real ao /ws e mede o tempo entre o fim do
áudio e o primeiro som da resposta (lado do cliente), e lê a latência que o
Core reporta no evento "system". Falha (código 1) se a mediana passar 1300 ms.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

TARGET_MS = 1300
_TRAILING_SILENCE_S = 1.0
_TIMEOUT_S = 20.0


def summarise(values: list[int]) -> dict:
    if not values:
        return {"median": None, "p90": None, "n": 0}
    ordered = sorted(values)
    p90 = (
        statistics.quantiles(ordered, n=10, method="inclusive")[-1]
        if len(ordered) > 1
        else ordered[0]
    )
    return {"median": round(statistics.median(ordered)), "p90": round(p90), "n": len(ordered)}


def exit_code(summary: dict) -> int:
    median = summary["median"]
    return 0 if median is not None and median <= TARGET_MS else 1


async def _one_run(url: str, wav: Path) -> tuple[int | None, int | None]:
    import websockets
    from pipecat.serializers.protobuf import ProtobufFrameSerializer

    from tests.voice.gpu_client import CHUNK_MS, encode_audio, is_audio, read_wav, rtvi_event

    serializer = ProtobufFrameSerializer()
    pcm = read_wav(wav) + b"\x00\x00" * int(16000 * _TRAILING_SILENCE_S)
    chunks = await encode_audio(serializer, pcm)
    async with websockets.connect(url, max_size=None) as ws:
        # Como a app: só falar depois de o pipeline estar pronto.
        while True:
            event = rtvi_event(await serializer.deserialize(await ws.recv()))
            if event and event["type"] == "state":
                break
        for chunk in chunks:
            await ws.send(chunk)
            await asyncio.sleep(CHUNK_MS / 1000)  # tempo real, como um microfone
        sent_at = time.monotonic() - _TRAILING_SILENCE_S
        client_ms = server_ms = None
        deadline = time.monotonic() + _TIMEOUT_S
        while time.monotonic() < deadline and (client_ms is None or server_ms is None):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            except TimeoutError:
                break
            frame = await serializer.deserialize(raw)
            if client_ms is None and is_audio(frame):
                client_ms = round((time.monotonic() - sent_at) * 1000)
            event = rtvi_event(frame)
            if event and event["type"] == "system" and event["data"].get("latency_ms"):
                server_ms = event["data"]["latency_ms"]
    return client_ms, server_ms


async def _main(args: argparse.Namespace) -> int:
    import httpx

    base = f"http://{args.host}:{args.port}"
    token = httpx.get(f"{base}/pair").json()["token"]
    url = f"ws://{args.host}:{args.port}/ws?token={token}"
    wavs = sorted(Path(args.audio_dir).glob("*.wav"))
    if not wavs:
        print(f"Sem .wav em {args.audio_dir}")
        return 1
    client, server = [], []
    for wav in wavs:
        for _ in range(args.runs):
            c, s = await _one_run(url, wav)
            print(f"{wav.name}: cliente={c} ms, core={s} ms")
            client += [c] if c is not None else []
            server += [s] if s is not None else []
    c_sum, s_sum = summarise(client), summarise(server)
    print(f"\n{'medição':<10}{'mediana':>10}{'p90':>10}{'n':>6}")
    for name, s in (("cliente", c_sum), ("core", s_sum)):
        print(f"{name:<10}{s['median']!s:>10}{s['p90']!s:>10}{s['n']:>6}")
    print(f"\nObjetivo: mediana ≤ {TARGET_MS} ms (cliente).")
    return exit_code(c_sum)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", default="recordings")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    sys.exit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
