from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.tests.utils import run_test

from friday.config import Config, TtsConfig
from friday.llm.providers import SlowResponseWatch
from friday.metrics import TurnTimer
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import ToolRegistry
from friday.voice.processors import ReplyTap, VoiceDeps

from .test_processors import FakeMemory


def _tap(timer=None, watch=None):
    deps = VoiceDeps(ToolRegistry(), ConfirmationManager(), FakeMemory())
    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    return ReplyTap(cfg, deps, watch or SlowResponseWatch(99.0), timer or TurnTimer()), deps


def _events(frames):
    return [f.data for f in frames if isinstance(f, RTVIServerMessageFrame)]


async def test_assistant_reply_is_logged_and_sent():
    tap, deps = _tap()
    frames = [
        LLMFullResponseStartFrame(),
        LLMTextFrame("Olá, "),
        LLMTextFrame("Fábio."),
        LLMFullResponseEndFrame(),
    ]
    down, _ = await run_test(tap, frames_to_send=frames)
    assert {"type": "transcript", "data": {"role": "assistant", "text": "Olá, Fábio."}} in _events(
        down
    )
    assert deps.memory.turns == [("assistant", "Olá, Fábio.")]


async def test_first_token_stops_filler():
    watch = SlowResponseWatch(0.0, clock=lambda: 5.0)
    watch.start()
    tap, _ = _tap(watch=watch)
    await run_test(tap, frames_to_send=[LLMFullResponseStartFrame(), LLMTextFrame("x")])
    assert watch.should_say_filler() is False


async def test_bot_speaking_sends_state_and_latency():
    t = [0.0]
    timer = TurnTimer(clock=lambda: t[0])
    timer.mark("speech_end")
    t[0] = 0.9
    tap, _ = _tap(timer=timer)
    down, up = await run_test(
        tap,
        frames_to_send=[BotStartedSpeakingFrame()],
        frames_to_send_direction=FrameDirection.UPSTREAM,
    )
    events = _events(down)
    assert {"type": "state", "data": {"value": "speaking"}} in events
    system = next(e for e in events if e["type"] == "system")
    assert system["data"]["latency_ms"] == 900
    assert system["data"]["model"] == "qwen3:8b"


async def test_vad_stop_marks_speech_end():
    t = [1.0]
    timer = TurnTimer(clock=lambda: t[0])
    tap, _ = _tap(timer=timer)
    # O fim real da fala (VAD), não o fim do turno, que já inclui o STT.
    await run_test(tap, frames_to_send=[VADUserStoppedSpeakingFrame()])
    t[0] = 1.5
    timer.mark("stt_done")
    assert timer.report() == {"stt_done": 500}


async def test_system_event_reports_current_voice():
    deps = VoiceDeps(ToolRegistry(), ConfirmationManager(), FakeMemory())
    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    tap = ReplyTap(cfg, deps, SlowResponseWatch(99.0), TurnTimer(), current_lang=lambda: "en")
    down, _ = await run_test(
        tap,
        frames_to_send=[BotStartedSpeakingFrame()],
        frames_to_send_direction=FrameDirection.UPSTREAM,
    )
    system = next(e for e in _events(down) if e["type"] == "system")
    assert system["data"]["voice"] == "en_GB-x"
