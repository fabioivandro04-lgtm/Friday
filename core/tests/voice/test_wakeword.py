from friday.voice.wakeword import WakeGate


def test_phrase_admits_case_and_accent_insensitive():
    assert WakeGate(["friday"]).admit("Olá FRIDAY, que horas são?") is True


def test_closed_gate_drops_other_speech():
    assert WakeGate(["friday"]).admit("que horas são?") is False


def test_awake_state_comes_from_outside():
    # O Pipecat decide quando acorda e quando volta a dormir (fonte única de verdade).
    gate = WakeGate(["friday"])
    gate.set_awake(True)
    assert gate.admit("e depois?") is True
    gate.set_awake(False)
    assert gate.admit("e depois?") is False


def test_phrase_must_be_a_word():
    assert WakeGate(["friday"]).admit("fridays are great") is False
