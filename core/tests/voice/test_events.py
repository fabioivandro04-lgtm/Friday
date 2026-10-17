from friday.tools.confirm import PendingAction
from friday.voice.events import confirm_cleared, confirm_request, state, system, transcript


def test_state():
    assert state("thinking") == {"type": "state", "data": {"value": "thinking"}}


def test_transcript():
    assert transcript("user", "olá") == {
        "type": "transcript",
        "data": {"role": "user", "text": "olá"},
    }


def test_confirm_request_and_cleared():
    action = PendingAction(id="a1", tool="send", args={"to": "x"}, summary="Enviar a x")
    assert confirm_request(action) == {
        "type": "confirm_request",
        "data": {"id": "a1", "summary": "Enviar a x"},
    }
    assert confirm_cleared("a1") == {"type": "confirm_cleared", "data": {"id": "a1"}}


def test_system_with_error():
    assert system("qwen3:8b", "pt_PT", 900, 7.5, error="Modelo local indisponível") == {
        "type": "system",
        "data": {
            "model": "qwen3:8b",
            "voice": "pt_PT",
            "latency_ms": 900,
            "vram_used_gb": 7.5,
            "error": "Modelo local indisponível",
        },
    }
