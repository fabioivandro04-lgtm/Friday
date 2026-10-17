import json
import stat

import pytest

from friday.integrations.auth import GoogleTokenSource, MicrosoftTokenSource, write_private


def test_write_private_is_owner_only(tmp_path):
    p = tmp_path / "s" / "t.json"
    write_private(p, "{}")
    assert p.read_text() == "{}"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


class FakeCreds:
    def __init__(self, valid):
        self.valid = valid
        self.token = "old"
        self.refreshed = False

    def refresh(self, request):
        self.refreshed, self.valid, self.token = True, True, "new"

    def to_json(self):
        return json.dumps({"token": self.token})


async def test_google_refreshes_and_saves(tmp_path):
    path = tmp_path / "google_token.json"
    creds = FakeCreds(valid=False)
    src = GoogleTokenSource(path, loader=lambda p: creds)
    assert await src.get_token() == "new"
    assert creds.refreshed
    assert json.loads(path.read_text())["token"] == "new"


async def test_google_valid_token_is_reused(tmp_path):
    creds = FakeCreds(valid=True)
    src = GoogleTokenSource(tmp_path / "g.json", loader=lambda p: creds)
    assert await src.get_token() == "old" and not creds.refreshed


class FakeMsalApp:
    def __init__(self, result):
        self.result = result

    def get_accounts(self):
        return [{"username": "fabio@x.pt"}]

    def acquire_token_silent(self, scopes, account):
        return self.result


class FakeCache:
    has_state_changed = True

    def serialize(self):
        return '{"cache": 1}'


async def test_microsoft_silent_token_and_cache_saved(tmp_path):
    path = tmp_path / "ms.json"
    src = MicrosoftTokenSource(FakeMsalApp({"access_token": "ms-tok"}), FakeCache(), path)
    assert await src.get_token() == "ms-tok"
    assert path.read_text() == '{"cache": 1}'


async def test_microsoft_without_login_raises(tmp_path):
    src = MicrosoftTokenSource(FakeMsalApp(None), FakeCache(), tmp_path / "ms.json")
    with pytest.raises(RuntimeError, match="connect microsoft"):
        await src.get_token()
