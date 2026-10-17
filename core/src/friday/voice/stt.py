"""Whisper com deteção automática de língua (PT/EN) por frase."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.utils.time import time_now_iso8601

_NO_SPEECH_THRESHOLD = 0.4
_SUPPORTED = ("pt", "en")


@dataclass(frozen=True)
class SttResult:
    text: str
    language: str | None
    probability: float
    avg_logprob: float


def summarise_segments(
    segments: Iterable[Any], language: str | None, probability: float, no_speech_threshold: float
) -> SttResult:
    speech = [s for s in segments if s.no_speech_prob < no_speech_threshold]
    text = "".join(s.text for s in speech).strip()
    avg = sum(s.avg_logprob for s in speech) / len(speech) if speech else 0.0
    return SttResult(text, language, probability, avg)


class FridayWhisperSTT(WhisperSTTService):
    """Igual ao WhisperSTTService, mas deixa o Whisper detetar a língua e guarda a confiança.

    O `SttResult` segue no campo `result` do `TranscriptionFrame`. Com `shared`, usa o
    modelo já carregado em vez de carregar outro (cada sessão e chamada reutiliza-o).
    """

    def __init__(self, *args: Any, shared: Any = None, **kwargs: Any) -> None:
        self._shared = shared
        super().__init__(*args, **kwargs)

    def _load(self) -> None:
        if self._shared is not None:
            self._model = self._shared.get()
        else:
            super()._load()

    def _run(self, audio_float: np.ndarray, language: str | None):
        segments, info = self._model.transcribe(
            audio_float,
            language=language,
            vad_filter=False,
            condition_on_previous_text=False,
            hotwords="Friday",  # o nome dela no meio de português
        )
        # `segments` é um gerador: a transcrição acontece ao iterar, por isso fica nesta thread.
        return list(segments), info

    def _transcribe(self, audio_float: np.ndarray) -> SttResult:
        segments, info = self._run(audio_float, None)
        language, probability = info.language, info.language_probability
        if language not in _SUPPORTED:
            # A Friday só fala PT e EN: volta a transcrever na mais provável das duas.
            probs = dict(getattr(info, "all_language_probs", None) or [])
            pt, en = probs.get("pt", 0.0), probs.get("en", 0.0)
            language = "pt" if pt >= en else "en"
            probability = max(pt, en) / (pt + en) if pt + en else 0.0
            segments, _ = self._run(audio_float, language)
        return summarise_segments(segments, language, probability, _NO_SPEECH_THRESHOLD)

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if not self._model:
            yield ErrorFrame("Whisper model not available")
            return
        await self.start_processing_metrics()
        audio_float = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        result = await asyncio.to_thread(self._transcribe, audio_float)
        await self.stop_processing_metrics()
        logger.debug(f"{self}: {len(audio) / 32000:.2f}s de áudio → {result}")
        if not result.text:
            return  # ruído ou silêncio: não responder
        yield TranscriptionFrame(
            result.text, self._user_id, time_now_iso8601(), result.language, result=result
        )
