"""Quem pode falar com a Friday: só este PC e a rede Tailscale, com token."""

from __future__ import annotations

import hmac
import ipaddress
import os
import secrets
from pathlib import Path

_ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.1/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("100.64.0.0/10"),  # endereços Tailscale (CGNAT)
]
_LOCALHOST = {"127.0.0.1", "::1"}


def is_allowed_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _ALLOWED_NETWORKS if addr.version == net.version)


def is_localhost(ip: str) -> bool:
    return ip in _LOCALHOST


class TokenStore:
    """Token de emparelhamento, guardado num ficheiro só legível pelo utilizador."""

    def __init__(self, path: Path, fixed: str | None = None) -> None:
        self._path = Path(path)
        self._fixed = fixed

    def get_or_create(self) -> str:
        if self._fixed:
            return self._fixed
        if self._path.exists():
            return self._path.read_text(encoding="utf-8").strip()
        token = secrets.token_urlsafe(32)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
        return token

    def check(self, token: str) -> bool:
        return hmac.compare_digest(token.encode(), self.get_or_create().encode())


# Nomes por que o Core pode ser chamado. Outro nome no cabeçalho Host indica
# DNS rebinding (um site a fingir ser 127.0.0.1) e é recusado.
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "testserver"}
_APP_ORIGINS = {"tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"}


def _hostname(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):  # [::1]:8765
        return value[1 : value.find("]")]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def is_allowed_host(host_header: str) -> bool:
    name = _hostname(host_header)
    return name in _LOCAL_NAMES or name.endswith(".ts.net") or is_allowed_ip(name)


def is_allowed_origin(origin: str | None) -> bool:
    if not origin:  # clientes que não são browsers (testes, script de medição)
        return True
    origin = origin.strip().lower()
    if origin in _APP_ORIGINS:
        return True
    scheme, _, rest = origin.partition("://")
    return scheme in ("http", "https") and is_allowed_host(rest)
