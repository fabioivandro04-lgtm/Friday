"""Descarrega vozes Piper com URLs bem codificados (o downloader do Piper falha com "ã")."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _urlopen_bytes(url: str) -> bytes:
    with urlopen(url) as response:  # noqa: S310 (URL fixo do Hugging Face)
        return response.read()


def piper_voice_urls(voice_id: str) -> tuple[str, str]:
    lang_code, name, quality = voice_id.split("-")
    family = lang_code.split("_")[0]
    path = quote(f"{family}/{lang_code}/{name}/{quality}/{voice_id}")
    model = f"{_BASE}/{path}.onnx?download=true"
    return model, f"{_BASE}/{path}.onnx.json?download=true"


def ensure_piper_voice(
    voice_id: str, download_dir: Path, fetch: Callable[[str], bytes] = _urlopen_bytes
) -> Path:
    download_dir = Path(download_dir)
    model_path = download_dir / f"{voice_id}.onnx"
    config_path = download_dir / f"{voice_id}.onnx.json"
    if model_path.exists() and config_path.exists():
        return model_path
    download_dir.mkdir(parents=True, exist_ok=True)
    model_url, config_url = piper_voice_urls(voice_id)
    # O config primeiro: o Pipecat só verifica o .onnx, por isso esse fica para o fim.
    config_path.write_bytes(fetch(config_url))
    model_path.write_bytes(fetch(model_url))
    return model_path
