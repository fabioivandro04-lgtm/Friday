"""Processadores Pipecat da Friday: o "cérebro" da conversa e a escuta das respostas."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ManuallySwitchServiceFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIClientMessageFrame, RTVIServerMessageFrame
from pipecat.services.llm_service import LLMService
from pipecat.utils.errors import ErrorCategory

from friday.config import Config
from friday.llm.providers import SlowResponseWatch, filler_phrase
from friday.memory.store import MemoryStore
from friday.metrics import TurnTimer, vram_used_gb
from friday.persona import system_prompt
from friday.tools.confirm import (
    ConfirmationManager,
    PendingAction,
    is_hedge,
    parse_confirmation,
)
from friday.tools.registry import ToolRegistry
from friday.voice import events
from friday.voice.language import Lang, choose_language
from friday.voice.stt import SttResult
from friday.voice.wakeword import WakeGate

# Abaixo disto, o Whisper provavelmente ouviu mal: melhor pedir para repetir.
MIN_AVG_LOGPROB = -1.0

_SAY = {
    "pt": {
        "repeat": "Podes repetir?",
        "done": "Feito.",
        "cancelled": "Cancelado.",
        "ask_again": "Confirmas? Diz sim ou não.",
        "llm_down": "O modelo local não está a responder.",
    },
    "en": {
        "repeat": "Could you repeat that?",
        "done": "Done.",
        "cancelled": "Cancelled.",
        "ask_again": "Do you confirm? Say yes or no.",
        "llm_down": "The local model isn't responding.",
    },
}


def _is_llm_failure(frame: ErrorFrame) -> bool:
    """Só falhas do próprio LLM são ditas em voz; erros de ferramentas o LLM já explica."""
    if getattr(frame, "category", None) == ErrorCategory.APPLICATION:
        return False
    processor = getattr(frame, "processor", None)
    return processor is None or isinstance(processor, LLMService)


@dataclass
class VoiceDeps:
    registry: ToolRegistry
    confirmations: ConfirmationManager
    memory: MemoryStore


class FridayBrain(FrameProcessor):
    """Fica entre o STT e o agregador do utilizador.

    Escolhe a língua, trata as confirmações pendentes, atualiza o prompt com a
    memória e avisa a interface. Só deixa passar para o LLM o que é conversa.
    """

    def __init__(
        self,
        cfg: Config,
        deps: VoiceDeps,
        *,
        context: LLMContext,
        watch: SlowResponseWatch,
        tts: dict[Lang, FrameProcessor],
        timer: TurnTimer | None = None,
        wake: WakeGate | None = None,
    ) -> None:
        super().__init__(name="FridayBrain")
        self._wake = wake
        self._timer = timer or TurnTimer()
        self._cfg = cfg
        self._deps = deps
        self._context = context
        self._watch = watch
        self._tts = tts
        self.lang: Lang = "pt"
        self._bot_speaking = False
        self._filler_task: asyncio.Task | None = None
        self._asked_again: str | None = None

    async def emit(self, event: dict[str, Any]) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=event))

    async def say(self, key: str) -> None:
        await self.push_frame(TTSSpeakFrame(_SAY[self.lang][key], append_to_context=False))

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            await self._on_transcription(frame)
            return
        if isinstance(frame, RTVIClientMessageFrame):
            await self._on_client_message(frame.type, frame.data or {})
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        elif isinstance(frame, (UserStartedSpeakingFrame, InterruptionFrame)):
            # O utilizador voltou a falar: a frase de espera já não faz sentido.
            self._cancel_filler()
            # Interromper a Friday enquanto pergunta "confirmas?" anula a ação.
            if self._bot_speaking:
                await self._cancel_pending()
        elif isinstance(frame, ErrorFrame):
            # Depois de um erro já não vem resposta: nada de "Deixa-me ver…".
            self._cancel_filler()
            await self.emit(
                events.system(self._cfg.llm.local_model, self._voice(), None, None, frame.error)
            )
            if _is_llm_failure(frame):
                await self.say("llm_down")

        await self.push_frame(frame, direction)

    def _voice(self) -> str:
        return self._cfg.tts.voice_pt if self.lang == "pt" else self._cfg.tts.voice_en

    async def _on_transcription(self, frame: TranscriptionFrame) -> None:
        self._timer.mark("stt_done")
        text = frame.text.strip()
        if self._wake and not self._wake.admit(text):
            # Conversa que não é para a Friday: o agregador também a ignora.
            await self.push_frame(frame)
            return
        result = frame.result if isinstance(frame.result, SttResult) else None
        if result and result.avg_logprob < MIN_AVG_LOGPROB:
            await self.say("repeat")
            return

        lang = choose_language(
            result.language if result else None,
            result.probability if result else 0.0,
            text,
            self.lang,
        )
        if lang != self.lang:
            self.lang = lang
            await self.push_frame(ManuallySwitchServiceFrame(service=self._tts[lang]))

        await self.emit(events.transcript("user", text))

        await self._flush_expired()
        pending = self._deps.confirmations.pending()
        if pending is not None and await self._answer_pending(pending, text):
            return

        await self._refresh_system_prompt(text)
        await asyncio.to_thread(self._deps.memory.log_turn, "user", text)
        await self.emit(events.state("thinking"))
        self._start_filler_timer()
        await self.push_frame(frame)

    async def _answer_pending(self, pending: PendingAction, text: str) -> bool:
        """Trata a resposta a "confirmas?". Devolve False se a frase era outra conversa."""
        if parse_confirmation(text) == "unclear":
            if is_hedge(text) and self._asked_again != pending.id:
                self._asked_again = pending.id
                await self.say("ask_again")
                return True
            # Outra conversa (ou segunda hesitação): a ação é cancelada e a frase segue.
            await self._cancel_pending()
            return False
        resolution = self._deps.confirmations.resolve(text)
        if resolution == "confirmed":
            await self._run(pending)
            await self.say("done")
        else:
            await self.say("cancelled")
        await self.emit(events.confirm_cleared(pending.id))
        return True

    async def _flush_expired(self) -> None:
        expired = self._deps.confirmations.take_expired()
        if expired:
            await self.emit(events.confirm_cleared(expired))

    async def _on_client_message(self, type_: str, data: dict[str, Any]) -> None:
        await self._flush_expired()
        if type_ == "confirm":
            action = self._deps.confirmations.confirm_by_id(str(data.get("id", "")))
            if action is None:
                return
            await self._run(action)
            await self.emit(events.confirm_cleared(action.id))
            await self.say("done")
        elif type_ == "cancel":
            if await self._cancel_pending():
                await self.say("cancelled")

    async def _cancel_pending(self) -> bool:
        pending = self._deps.confirmations.pending()
        if pending is None:
            return False
        self._deps.confirmations.cancel()
        await self.emit(events.confirm_cleared(pending.id))
        return True

    async def _run(self, action: PendingAction) -> str:
        return await self._deps.registry.get(action.tool).handler(**action.args)

    async def _refresh_system_prompt(self, text: str) -> None:
        # Embeddings + SQLite numa thread, para não atrasar o áudio.
        memory = await asyncio.to_thread(self._deps.memory.context_for, text)
        prompt = system_prompt(self.lang, memory)
        if self._cfg.llm.provider == "local" and self._cfg.llm.local_model.startswith("qwen3"):
            prompt += "\n/no_think"  # desliga o raciocínio do Qwen3 (mais rápido)
        others = [m for m in self._context.messages if m.get("role") != "system"]
        self._context.set_messages([{"role": "system", "content": prompt}, *others])

    def _cancel_filler(self) -> None:
        self._watch.first_token()
        if self._filler_task:
            self._filler_task.cancel()

    def _start_filler_timer(self) -> None:
        if self._filler_task:
            self._filler_task.cancel()
        self._watch.start()
        self._filler_task = asyncio.get_running_loop().create_task(self._filler_later())

    async def _filler_later(self) -> None:
        await asyncio.sleep(self._cfg.llm.slow_threshold_s)
        if self._watch.should_say_filler():
            await self.push_frame(TTSSpeakFrame(filler_phrase(self.lang), append_to_context=False))

    async def cleanup(self) -> None:
        if self._filler_task:
            self._filler_task.cancel()
        await super().cleanup()


class ReplyTap(FrameProcessor):
    """Fica depois do LLM: regista a resposta, o estado da voz e a latência para a interface."""

    def __init__(
        self,
        cfg: Config,
        deps: VoiceDeps,
        watch: SlowResponseWatch,
        timer: TurnTimer,
        current_lang: Callable[[], Lang] = lambda: "pt",
    ) -> None:
        super().__init__(name="ReplyTap")
        self._cfg = cfg
        self._deps = deps
        self._watch = watch
        self._timer = timer
        self._buffer: list[str] = []
        self._current_lang = current_lang

    async def emit(self, event: dict[str, Any]) -> None:
        await self.push_frame(RTVIServerMessageFrame(data=event))

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            # O fim real da fala; o fim do turno (UserStopped…) já inclui o STT.
            self._timer.mark("speech_end")
        elif isinstance(frame, LLMFullResponseStartFrame):
            self._buffer = []
        elif isinstance(frame, LLMTextFrame):
            self._timer.mark("llm_first_token")
            self._watch.first_token()
            self._buffer.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._buffer).strip()
            self._buffer = []
            if text:
                await asyncio.to_thread(self._deps.memory.log_turn, "assistant", text)
                await self.emit(events.transcript("assistant", text))
        elif isinstance(frame, BotStartedSpeakingFrame) and direction == FrameDirection.UPSTREAM:
            self._timer.mark("tts_first_audio")
            await self.emit(events.state("speaking"))
            await self._emit_system()
        elif isinstance(frame, BotStoppedSpeakingFrame) and direction == FrameDirection.UPSTREAM:
            await self.emit(events.state("listening"))

    async def _emit_system(self) -> None:
        voice = self._cfg.tts.voice_pt if self._current_lang() == "pt" else self._cfg.tts.voice_en
        latency = self._timer.report().get("total_ms")
        model = (
            self._cfg.llm.local_model
            if self._cfg.llm.provider == "local"
            else (self._cfg.llm.cloud_model or self._cfg.llm.local_model)
        )
        vram = await asyncio.to_thread(vram_used_gb)
        await self.emit(events.system(model, voice, latency, vram))
