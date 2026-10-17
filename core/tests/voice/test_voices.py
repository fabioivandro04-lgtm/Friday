from friday.voice.voices import ensure_piper_voice, piper_voice_urls

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def test_urls_are_percent_encoded():
    model, config = piper_voice_urls("pt_PT-tugão-medium")
    assert model == f"{BASE}/pt/pt_PT/tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx?download=true"
    assert config == model.replace(".onnx?", ".onnx.json?")
    model.encode("ascii")  # não pode rebentar como o downloader do Piper


def test_downloads_both_files_once(tmp_path):
    fetched = []

    def fetch(url):
        fetched.append(url)
        return b"data"

    path = ensure_piper_voice("en_GB-alan-medium", tmp_path, fetch=fetch)
    assert path == tmp_path / "en_GB-alan-medium.onnx"
    assert path.read_bytes() == b"data"
    assert (tmp_path / "en_GB-alan-medium.onnx.json").exists()
    ensure_piper_voice("en_GB-alan-medium", tmp_path, fetch=fetch)
    assert len(fetched) == 2


def test_partial_download_does_not_leave_model(tmp_path):
    def fetch(url):
        if url.endswith(".json?download=true"):
            raise OSError("rede")
        return b"data"

    try:
        ensure_piper_voice("en_GB-alan-medium", tmp_path, fetch=fetch)
    except OSError:
        pass
    assert not (tmp_path / "en_GB-alan-medium.onnx").exists()
