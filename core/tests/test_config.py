import pytest

from friday.config import load_config


def test_defaults_when_file_has_only_tts(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "pt.onnx"\nvoice_en = "en.onnx"\n')
    cfg = load_config(p, env={})
    assert cfg.llm.local_model == "qwen3:8b"
    assert cfg.stt.model == "large-v3-turbo"
    assert cfg.server.port == 8765
    assert cfg.llm.cloud_api_key is None
    assert cfg.tts.voice_pt == "pt.onnx"


def test_env_overrides_secrets(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n[llm]\ncloud_model = "x/y"\n')
    cfg = load_config(p, env={"OPENROUTER_API_KEY": "k", "FRIDAY_TOKEN": "t"})
    assert cfg.llm.cloud_api_key == "k"
    assert cfg.llm.cloud_model == "x/y"
    assert cfg.server.token == "t"


def test_secrets_in_toml_are_ignored(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n[llm]\ncloud_api_key = "leak"\n')
    assert load_config(p, env={}).llm.cloud_api_key is None


def test_missing_tts_voices_raises(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text("")
    with pytest.raises(ValueError, match="voice_pt"):
        load_config(p, env={})


def test_tts_download_dir_default(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "pt_PT-tugão-medium"\nvoice_en = "en_GB-alan-medium"\n')
    assert load_config(p, env={}).tts.download_dir == "models/piper"


def test_wake_word_defaults_off(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n')
    wake = load_config(p, env={}).wake
    assert wake.enabled is False
    assert wake.phrases == ["friday"]
    assert wake.window_s == 15.0


def test_wake_word_enabled(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n[wake]\nenabled = true\n')
    assert load_config(p, env={}).wake.enabled is True


def test_unknown_keys_are_warned(tmp_path, caplog):
    import logging

    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n[llm]\nlocal_modle = "x"\n')
    with caplog.at_level(logging.WARNING, logger="friday"):
        load_config(p, env={})
    assert "llm.local_modle" in caplog.text


def test_integrations_defaults(tmp_path):
    p = tmp_path / "friday.toml"
    p.write_text('[tts]\nvoice_pt = "a"\nvoice_en = "b"\n')
    i = load_config(p, env={}).integrations
    assert i.timezone == "Europe/Lisbon"
    assert i.secrets_dir == "secrets"
    assert i.microsoft_client_id is None
