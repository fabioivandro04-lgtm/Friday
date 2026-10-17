from types import SimpleNamespace as S

from friday.voice.stt import summarise_segments


def test_joins_speech_segments_and_averages_logprob():
    segs = [
        S(text=" Olá Friday,", no_speech_prob=0.1, avg_logprob=-0.2),
        S(text=" que horas são?", no_speech_prob=0.1, avg_logprob=-0.4),
    ]
    r = summarise_segments(segs, "pt", 0.97, no_speech_threshold=0.4)
    assert r.text == "Olá Friday, que horas são?"
    assert r.language == "pt" and r.probability == 0.97
    assert abs(r.avg_logprob - (-0.3)) < 1e-9


def test_drops_non_speech_segments():
    segs = [
        S(text=" ruído", no_speech_prob=0.9, avg_logprob=-2.0),
        S(text=" sim", no_speech_prob=0.1, avg_logprob=-0.1),
    ]
    r = summarise_segments(segs, "pt", 0.5, no_speech_threshold=0.4)
    assert r.text == "sim" and r.avg_logprob == -0.1


def test_empty_when_no_speech():
    r = summarise_segments([], "en", 0.0, no_speech_threshold=0.4)
    assert r.text == "" and r.avg_logprob == 0.0


def test_transcribe_detects_language_and_filters_silence():
    import numpy as np

    from friday.voice.stt import FridayWhisperSTT

    calls = {}

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            calls.update(kwargs)
            seg = S(text=" olá", no_speech_prob=0.0, avg_logprob=-0.1)
            return iter([seg]), S(language="pt", language_probability=0.9)

    stt = FridayWhisperSTT.__new__(FridayWhisperSTT)
    stt._model = FakeModel()
    r = stt._transcribe(np.zeros(16000, dtype=np.float32))
    assert r.text == "olá" and r.language == "pt"
    assert calls["language"] is None
    assert calls["vad_filter"] is True
    assert calls["condition_on_previous_text"] is False
    assert calls["hotwords"] == "Friday"


def test_other_language_is_retranscribed_as_best_of_pt_en():
    import numpy as np

    from friday.voice.stt import FridayWhisperSTT

    calls = []

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            calls.append(kwargs["language"])
            if kwargs["language"] is None:
                info = S(
                    language="nl",
                    language_probability=0.6,
                    all_language_probs=[("nl", 0.6), ("pt", 0.3), ("en", 0.05)],
                )
                return iter([S(text=" blijf", no_speech_prob=0.0, avg_logprob=-0.9)]), info
            seg = S(text=" Olá Friday", no_speech_prob=0.0, avg_logprob=-0.2)
            return iter([seg]), S(language=kwargs["language"], language_probability=1.0)

    stt = FridayWhisperSTT.__new__(FridayWhisperSTT)
    stt._model = FakeModel()
    r = stt._transcribe(np.zeros(16000, dtype=np.float32))
    assert calls == [None, "pt"]
    assert r.text == "Olá Friday" and r.language == "pt"
    assert abs(r.probability - 0.3 / 0.35) < 1e-9  # PT vs EN, normalizado
