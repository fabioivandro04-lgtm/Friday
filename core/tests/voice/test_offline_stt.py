from types import SimpleNamespace as S

from friday.voice.offline_stt import FileTranscriber


async def test_transcribes_bytes_and_loads_model_once():
    loads = []

    class Model:
        def transcribe(self, audio, **kw):
            assert audio.read() == b"OGG"
            assert kw["vad_filter"] is True
            return iter([S(text=" que horas"), S(text=" são?")]), S(language="pt")

    def loader(name, device):
        loads.append((name, device))
        return Model()

    t = FileTranscriber("large-v3-turbo", "cuda", loader=loader)
    assert await t(b"OGG") == "que horas são?"
    assert await t(b"OGG") == "que horas são?"
    assert loads == [("large-v3-turbo", "cuda")]
