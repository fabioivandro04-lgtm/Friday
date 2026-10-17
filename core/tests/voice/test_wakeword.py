from friday.voice.wakeword import WakeGate


def _gate(t):
    return WakeGate(["friday"], window_s=15.0, clock=lambda: t[0])


def test_gate_opens_on_phrase_case_and_accent_insensitive():
    t = [0.0]
    gate = _gate(t)
    assert gate.feed("Olá FRIDAY, que horas são?") is True


def test_gate_stays_closed_without_phrase():
    t = [0.0]
    gate = _gate(t)
    assert gate.feed("que horas são?") is False


def test_gate_stays_open_within_window_and_extends():
    t = [0.0]
    gate = _gate(t)
    gate.feed("friday")
    t[0] = 10.0
    assert gate.feed("e amanhã?") is True
    t[0] = 24.0
    assert gate.feed("e depois?") is True  # janela renovada aos 10 s


def test_gate_closes_after_window():
    t = [0.0]
    gate = _gate(t)
    gate.feed("friday")
    t[0] = 15.1
    assert gate.feed("e amanhã?") is False


def test_phrase_must_be_a_word():
    t = [0.0]
    assert _gate(t).feed("fridays are great") is False
