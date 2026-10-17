import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    ManuallySwitchServiceFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIClientMessageFrame, RTVIServerMessageFrame
from pipecat.tests.utils import run_test

from friday.config import Config, TtsConfig
from friday.llm.providers import SlowResponseWatch
from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import Tool, ToolRegistry
from friday.voice.pipeline import VoiceDeps
from friday.voice.processors import FridayBrain
from friday.voice.stt import SttResult


class FakeMemory:
    def __init__(self):
        self.turns = []

    def context_for(self, query):
        return "O Fábio prefere reuniões de manhã."

    def log_turn(self, role, text):
        self.turns.append((role, text))


@pytest.fixture
def sent():
    return []


@pytest.fixture
def deps(sent):
    async def send(to: str) -> str:
        sent.append(to)
        return "enviado"

    reg = ToolRegistry()
    reg.register(
        Tool("send", "Envia", {}, send, mutating=True, summary=lambda a: f"Enviar a {a['to']}")
    )
    return VoiceDeps(registry=reg, confirmations=ConfirmationManager(), memory=FakeMemory())


@pytest.fixture
def tts():
    return {"pt": FrameProcessor(name="tts-pt"), "en": FrameProcessor(name="tts-en")}


@pytest.fixture
def context():
    return LLMContext()


@pytest.fixture
def brain(deps, tts, context):
    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    return FridayBrain(cfg, deps, context=context, watch=SlowResponseWatch(99.0), tts=tts)


def _tr(text, lang="pt", prob=0.95, logprob=-0.2):
    return TranscriptionFrame(text, "u", "t", lang, result=SttResult(text, lang, prob, logprob))


def _events(frames):
    return [f.data for f in frames if isinstance(f, RTVIServerMessageFrame)]


def _spoken(frames):
    return [f.text for f in frames if isinstance(f, TTSSpeakFrame)]


async def test_normal_turn_is_forwarded_with_prompt_and_events(brain, context, deps):
    down, _ = await run_test(brain, frames_to_send=[_tr("que tempo faz hoje em Lisboa")])
    assert any(isinstance(f, TranscriptionFrame) for f in down)
    events = _events(down)
    assert {
        "type": "transcript",
        "data": {"role": "user", "text": "que tempo faz hoje em Lisboa"},
    } in events
    assert {"type": "state", "data": {"value": "thinking"}} in events
    system = context.messages[0]
    assert system["role"] == "system" and "reuniões de manhã" in system["content"]
    assert deps.memory.turns == [("user", "que tempo faz hoje em Lisboa")]


async def test_low_confidence_asks_to_repeat(brain):
    down, _ = await run_test(brain, frames_to_send=[_tr("hum coisa", logprob=-1.5)])
    assert _spoken(down) == ["Podes repetir?"]
    assert not any(isinstance(f, TranscriptionFrame) for f in down)


async def test_english_switches_voice(brain, tts):
    down, _ = await run_test(brain, frames_to_send=[_tr("what is the weather tomorrow", "en")])
    switches = [f for f in down if isinstance(f, ManuallySwitchServiceFrame)]
    assert [s.service for s in switches] == [tts["en"]]
    assert "English" in brain._context.messages[0]["content"]


async def test_spoken_yes_runs_pending_action(brain, deps, sent):
    action = deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    down, _ = await run_test(brain, frames_to_send=[_tr("sim")])
    assert sent == ["João"]
    assert _spoken(down) == ["Feito."]
    assert {"type": "confirm_cleared", "data": {"id": action.id}} in _events(down)
    assert not any(isinstance(f, TranscriptionFrame) for f in down)


async def test_spoken_no_cancels(brain, deps, sent):
    deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    down, _ = await run_test(brain, frames_to_send=[_tr("não")])
    assert sent == [] and _spoken(down) == ["Cancelado."]
    assert deps.confirmations.pending() is None


async def test_unclear_answer_keeps_pending_and_asks_again(brain, deps, sent):
    deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    down, _ = await run_test(brain, frames_to_send=[_tr("talvez")])
    assert sent == []
    assert _spoken(down) == ["Confirmas? Diz sim ou não."]
    assert deps.confirmations.pending() is not None


async def test_barge_in_cancels_pending_action(brain, deps, sent):
    action = deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    down, _ = await run_test(
        brain, frames_to_send=[BotStartedSpeakingFrame(), UserStartedSpeakingFrame()]
    )
    assert deps.confirmations.pending() is None and sent == []
    assert {"type": "confirm_cleared", "data": {"id": action.id}} in _events(down)


async def test_user_speaking_while_bot_silent_keeps_pending(brain, deps):
    deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    await run_test(brain, frames_to_send=[UserStartedSpeakingFrame()])
    assert deps.confirmations.pending() is not None


async def test_client_confirm_click_runs_action(brain, deps, sent):
    action = deps.confirmations.propose(deps.registry.get("send"), {"to": "Ana"})
    msg = RTVIClientMessageFrame(msg_id="1", type="confirm", data={"id": action.id})
    down, _ = await run_test(brain, frames_to_send=[msg])
    assert sent == ["Ana"] and _spoken(down) == ["Feito."]


async def test_client_cancel_click(brain, deps, sent):
    action = deps.confirmations.propose(deps.registry.get("send"), {"to": "Ana"})
    msg = RTVIClientMessageFrame(msg_id="1", type="cancel", data={})
    down, _ = await run_test(brain, frames_to_send=[msg])
    assert sent == [] and deps.confirmations.pending() is None
    assert {"type": "confirm_cleared", "data": {"id": action.id}} in _events(down)


async def test_stale_confirm_click_does_nothing(brain, deps, sent):
    deps.confirmations.propose(deps.registry.get("send"), {"to": "Ana"})
    msg = RTVIClientMessageFrame(msg_id="1", type="confirm", data={"id": "old"})
    await run_test(brain, frames_to_send=[msg])
    assert sent == []


def _fast_brain(deps, tts, context):
    from friday.config import LlmConfig

    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"), llm=LlmConfig(slow_threshold_s=0.05))
    return FridayBrain(cfg, deps, context=context, watch=SlowResponseWatch(0.05), tts=tts)


async def test_filler_when_llm_is_slow(deps, tts, context):
    from pipecat.tests.utils import SleepFrame

    brain = _fast_brain(deps, tts, context)
    down, _ = await run_test(
        brain, frames_to_send=[_tr("conta-me uma história longa"), SleepFrame(0.2)]
    )
    assert "Deixa-me ver…" in _spoken(down)


async def test_no_filler_after_llm_error(deps, tts, context):
    from pipecat.frames.frames import ErrorFrame
    from pipecat.tests.utils import SleepFrame

    brain = _fast_brain(deps, tts, context)
    down, _ = await run_test(
        brain,
        frames_to_send=[
            _tr("conta-me uma história longa"),
            SleepFrame(0.01),  # o erro do LLM chega depois da transcrição
            ErrorFrame("Connection error."),
            SleepFrame(0.2),
        ],
    )
    spoken = _spoken(down)
    assert "O modelo local não está a responder." in spoken
    assert "Deixa-me ver…" not in spoken


async def test_wake_gate_closed_forwards_silently(deps, tts, context):
    from friday.voice.wakeword import WakeGate

    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    gate = WakeGate(["friday"])
    brain = FridayBrain(
        cfg, deps, context=context, watch=SlowResponseWatch(99.0), tts=tts, wake=gate
    )
    down, _ = await run_test(brain, frames_to_send=[_tr("isto não é para ti, ok")])
    assert _events(down) == []
    assert deps.memory.turns == []


async def test_wake_gate_open_on_phrase(deps, tts, context):
    from friday.voice.wakeword import WakeGate

    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    gate = WakeGate(["friday"])
    brain = FridayBrain(
        cfg, deps, context=context, watch=SlowResponseWatch(99.0), tts=tts, wake=gate
    )
    down, _ = await run_test(brain, frames_to_send=[_tr("Friday, que horas são?")])
    assert {"type": "state", "data": {"value": "thinking"}} in _events(down)


async def test_something_else_cancels_pending_and_is_answered(brain, deps, sent):
    action = deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    down, _ = await run_test(brain, frames_to_send=[_tr("qual é o tempo amanhã em Lisboa")])
    assert sent == [] and deps.confirmations.pending() is None
    assert {"type": "confirm_cleared", "data": {"id": action.id}} in _events(down)
    assert "Confirmas? Diz sim ou não." not in _spoken(down)
    assert any(isinstance(f, TranscriptionFrame) for f in down)


async def test_second_hedge_cancels(brain, deps, sent):
    deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    down, _ = await run_test(brain, frames_to_send=[_tr("talvez"), _tr("não sei")])
    assert sent == [] and deps.confirmations.pending() is None
    assert _spoken(down).count("Confirmas? Diz sim ou não.") == 1


async def test_expired_action_clears_card_on_next_turn(deps, tts, context, sent):
    t = [0.0]
    deps.confirmations = ConfirmationManager(ttl_s=60, clock=lambda: t[0])
    action = deps.confirmations.propose(deps.registry.get("send"), {"to": "João"})
    t[0] = 61
    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    brain = FridayBrain(cfg, deps, context=context, watch=SlowResponseWatch(99.0), tts=tts)
    down, _ = await run_test(brain, frames_to_send=[_tr("sim, envia já isso")])
    assert sent == []
    assert {"type": "confirm_cleared", "data": {"id": action.id}} in _events(down)


async def test_wake_awake_from_pipecat_processes_follow_up(deps, tts, context):
    from friday.voice.wakeword import WakeGate

    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    gate = WakeGate(["friday"])
    gate.set_awake(True)  # o Pipecat ainda está acordado (a Friday falou há pouco)
    brain = FridayBrain(
        cfg, deps, context=context, watch=SlowResponseWatch(99.0), tts=tts, wake=gate
    )
    down, _ = await run_test(brain, frames_to_send=[_tr("e depois o que aconteceu")])
    assert {"type": "state", "data": {"value": "thinking"}} in _events(down)
