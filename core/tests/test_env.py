from friday.envfile import read_env_file


def test_reads_key_values_and_ignores_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# chave\nOPENROUTER_API_KEY=sk-123\nFRIDAY_TOKEN="abc"\n\nEMPTY=\n')
    assert read_env_file(p) == {"OPENROUTER_API_KEY": "sk-123", "FRIDAY_TOKEN": "abc", "EMPTY": ""}


def test_missing_file_is_empty(tmp_path):
    assert read_env_file(tmp_path / "nope") == {}
