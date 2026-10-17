from friday.metrics import TurnTimer, vram_used_gb


def test_turn_timer_report():
    t = [10.0]
    tt = TurnTimer(clock=lambda: t[0])
    tt.mark("speech_end")
    t[0] = 10.25
    tt.mark("stt_done")
    t[0] = 10.6
    tt.mark("llm_first_token")
    t[0] = 10.7
    tt.mark("tts_first_audio")
    assert tt.report() == {
        "stt_done": 250,
        "llm_first_token": 600,
        "tts_first_audio": 700,
        "total_ms": 700,
    }


def test_report_without_audio_has_no_total():
    t = [0.0]
    tt = TurnTimer(clock=lambda: t[0])
    tt.mark("speech_end")
    t[0] = 0.3
    tt.mark("stt_done")
    assert tt.report() == {"stt_done": 300}


def test_first_mark_of_a_stage_wins_and_reset_clears():
    t = [0.0]
    tt = TurnTimer(clock=lambda: t[0])
    tt.mark("speech_end")
    t[0] = 0.1
    tt.mark("llm_first_token")
    t[0] = 0.9
    tt.mark("llm_first_token")  # tokens seguintes não contam
    assert tt.report() == {"llm_first_token": 100}
    tt.reset()
    assert tt.report() == {}


def test_marks_before_speech_end_are_ignored():
    tt = TurnTimer(clock=lambda: 1.0)
    tt.mark("stt_done")
    assert tt.report() == {}


def test_vram_none_without_nvidia(monkeypatch):
    import pynvml

    def boom():
        raise pynvml.NVMLError(1)

    monkeypatch.setattr(pynvml, "nvmlInit", boom)
    assert vram_used_gb() is None
