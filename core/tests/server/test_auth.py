import stat

import pytest

from friday.server.auth import TokenStore, is_allowed_ip


@pytest.mark.parametrize(
    "ip,ok",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("100.101.5.9", True),
        ("100.127.255.254", True),
        ("100.128.0.1", False),
        ("192.168.1.20", False),
        ("8.8.8.8", False),
        ("not-an-ip", False),
    ],
)
def test_is_allowed_ip(ip, ok):
    assert is_allowed_ip(ip) is ok


def test_token_persists_and_checks(tmp_path):
    path = tmp_path / "friday.token"
    token = TokenStore(path).get_or_create()
    assert len(token) >= 32
    assert TokenStore(path).get_or_create() == token
    assert TokenStore(path).check(token) is True
    assert TokenStore(path).check("wrong") is False
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_fixed_token_overrides_file(tmp_path):
    store = TokenStore(tmp_path / "t", fixed="abc")
    assert store.get_or_create() == "abc"
    assert store.check("abc") is True
