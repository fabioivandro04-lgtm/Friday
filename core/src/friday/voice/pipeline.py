"""Monta o pipeline de voz da Friday: ouvir → pensar → falar, em streaming."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import WebSocket
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.service_switcher import ServiceSwitcher
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_start.wake_phrase_user_turn_start_strategy import (
    WakePhraseUserTurnStartStrategy,
)
from pipecat.turns.user_turn_strategies import (
    UserTurnStrategies,
    default_user_turn_start_strategies,
)
from pipecat.workers.runner import WorkerRunner

from friday.config import Config
from friday.integrations.panels import PanelFeeder
from friday.llm.providers import SlowResponseWatch, select_endpoint
from friday.metrics import TurnTimer
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import ToolRegistry, execute
from friday.voice import events
from friday.voice.processors import FridayBrain, ReplyTap, VoiceDeps
from friday.voice.session import SessionSlot
from friday.voice.stt import FridayWhisperSTT
from friday.voice.voices import ensure_piper_voice
from friday.voice.wakeword import WakeGate

__all__ = ["VoiceDeps", "run_voice_session", "tools_schema"]


def tools_schema(registry: ToolRegistry) -> ToolsSchema:
    schemas = []
    for spec in registry.schemas():
        fn = spec["function"]
        params = fn["parameters"]
        schemas.append(
            FunctionSchema(
                name=fn["name"],
                description=fn["description"],
                properties=params.get("properties", {}),
                required=params.get("required", []),
            )
        )
    return ToolsSchema(standard_tools=schemas)


# Push-to-talk: ao soltar a tecla o áudio para; fechar o turno depressa (padrão 1 s).
_AUDIO_IDLE_TIMEOUT_S = 0.3
_slot = SessionSlot()


async def run_voice_session(websocket: WebSocket, cfg: Config, deps: VoiceDeps) -> None:
    # Cada sessão tem as suas ações pendentes (o PC não confirma o que o telemóvel pediu).
    deps = replace(deps, confirmations=ConfirmationManager())
    await websocket.accept()
    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )

    # Carregar modelos bloqueia: fora do event loop, para não congelar o servidor.
    stt = await asyncio.to_thread(FridayWhisperSTT, model=cfg.stt.model, device=cfg.stt.device)

    endpoint = select_endpoint(cfg.llm)
    llm = OpenAILLMService(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
        settings=OpenAILLMService.Settings(
            model=endpoint.model, extra={"extra_body": endpoint.extra_body}
        ),
    )

    download_dir = Path(cfg.tts.download_dir)
    for voice_id in (cfg.tts.voice_pt, cfg.tts.voice_en):
        await asyncio.to_thread(ensure_piper_voice, voice_id, download_dir)
    tts = {
        lang: await asyncio.to_thread(PiperTTSService, voice_id=voice, download_dir=download_dir)
        for lang, voice in (("pt", cfg.tts.voice_pt), ("en", cfg.tts.voice_en))
    }
    tts_switcher = ServiceSwitcher(services=[tts["pt"], tts["en"]])

    context = LLMContext(tools=tools_schema(deps.registry))
    user_params = LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(), audio_idle_timeout=_AUDIO_IDLE_TIMEOUT_S
    )
    wake = None
    if cfg.wake.enabled:
        # Sempre à escuta: o Pipecat só abre um turno depois de ouvir "Friday",
        # e é ele que diz ao cérebro quando está acordado (uma só fonte de verdade).
        wake = WakeGate(cfg.wake.phrases)
        strategy = WakePhraseUserTurnStartStrategy(
            phrases=cfg.wake.phrases, timeout=cfg.wake.window_s
        )

        @strategy.event_handler("on_wake_phrase_detected")
        async def _on_wake(_strategy, _phrase) -> None:
            wake.set_awake(True)

        @strategy.event_handler("on_wake_phrase_timeout")
        async def _on_sleep(_strategy) -> None:
            wake.set_awake(False)

        user_params.user_turn_strategies = UserTurnStrategies(
            start=[strategy, *default_user_turn_start_strategies()]
        )
    aggregators = LLMContextAggregatorPair(context, user_params=user_params)
    watch = SlowResponseWatch(cfg.llm.slow_threshold_s)
    timer = TurnTimer()
    tz = ZoneInfo(cfg.integrations.timezone)
    feeder: PanelFeeder | None = None

    async def refresh_panels() -> None:
        if feeder:
            await feeder.refresh()

    brain = FridayBrain(
        cfg,
        deps,
        context=context,
        watch=watch,
        tts=tts,
        timer=timer,
        wake=wake,
        after_action=refresh_panels,
    )
    if deps.hub is not None:
        feeder = PanelFeeder(deps.hub, brain.emit, now=lambda: datetime.now(tz))
    panel_task: asyncio.Task | None = None
    tap = ReplyTap(cfg, deps, watch, timer, current_lang=lambda: brain.lang)

    async def call_tool(params: FunctionCallParams) -> None:
        result = await execute(
            deps.registry, deps.confirmations, params.function_name, dict(params.arguments)
        )
        pending = deps.confirmations.pending()
        if result.startswith("PENDENTE:") and pending is not None:
            await brain.emit(events.confirm_request(pending))
        await params.result_callback(result)

    for spec in deps.registry.schemas():
        llm.register_function(spec["function"]["name"], call_tool)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            brain,
            aggregators.user(),
            llm,
            tap,
            tts_switcher,
            transport.output(),
            aggregators.assistant(),
        ]
    )
    task = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True), enable_rtvi=True)

    @transport.event_handler("on_client_connected")
    async def _on_connected(_transport, _client) -> None:
        await brain.emit(events.state("listening"))
        await brain.emit(events.system(endpoint.model, cfg.tts.voice_pt, None, None))
        nonlocal panel_task
        if feeder:
            panel_task = asyncio.get_running_loop().create_task(feeder.run())

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client) -> None:
        deps.confirmations.cancel()
        if panel_task:
            panel_task.cancel()
        await task.cancel()

    holder = await _slot.claim(task.cancel)  # um novo dispositivo substitui o anterior
    try:
        await WorkerRunner(handle_sigint=False).run(task)
    finally:
        _slot.release(holder)
