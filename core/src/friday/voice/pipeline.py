"""Monta o pipeline de voz da Friday: ouvir → pensar → falar, em streaming."""

from __future__ import annotations

import asyncio
from pathlib import Path

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
from pipecat.workers.runner import WorkerRunner

from friday.config import Config
from friday.llm.providers import SlowResponseWatch, select_endpoint
from friday.tools.registry import ToolRegistry, execute
from friday.voice import events
from friday.voice.processors import FridayBrain, ReplyTap, VoiceDeps
from friday.voice.stt import FridayWhisperSTT
from friday.voice.voices import ensure_piper_voice

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


async def run_voice_session(websocket: WebSocket, cfg: Config, deps: VoiceDeps) -> None:
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

    stt = FridayWhisperSTT(model=cfg.stt.model, device=cfg.stt.device)

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
        "pt": PiperTTSService(voice_id=cfg.tts.voice_pt, download_dir=download_dir),
        "en": PiperTTSService(voice_id=cfg.tts.voice_en, download_dir=download_dir),
    }
    tts_switcher = ServiceSwitcher(services=[tts["pt"], tts["en"]])

    context = LLMContext(tools=tools_schema(deps.registry))
    aggregators = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    watch = SlowResponseWatch(cfg.llm.slow_threshold_s)
    brain = FridayBrain(cfg, deps, context=context, watch=watch, tts=tts)
    tap = ReplyTap(brain, deps, watch)

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

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client) -> None:
        deps.confirmations.cancel()
        await task.cancel()

    await WorkerRunner(handle_sigint=False).run(task)
