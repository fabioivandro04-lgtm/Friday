from friday.config import IntegrationsConfig
from friday.integrations.setup import build_hub


class Creds:
    valid, token = True, "t"


def test_no_accounts_means_empty_hub(tmp_path):
    hub = build_hub(IntegrationsConfig(secrets_dir=str(tmp_path)))
    assert hub.connected == []


def test_google_token_file_enables_google(tmp_path):
    (tmp_path / "google_token.json").write_text("{}")
    hub = build_hub(IntegrationsConfig(secrets_dir=str(tmp_path)), google_loader=lambda p: Creds())
    assert hub.connected == ["google"]


def test_microsoft_needs_client_id_and_cache(tmp_path):
    (tmp_path / "microsoft_cache.json").write_text("{}")
    made = []

    def factory(client_id, path):
        made.append(client_id)
        return object(), object()

    cfg = IntegrationsConfig(secrets_dir=str(tmp_path), microsoft_client_id="abc")
    hub = build_hub(cfg, microsoft_factory=factory)
    assert hub.connected == ["microsoft"] and made == ["abc"]
    assert build_hub(IntegrationsConfig(secrets_dir=str(tmp_path))).connected == []
