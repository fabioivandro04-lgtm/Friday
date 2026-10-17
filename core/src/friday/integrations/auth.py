"""Login no Google e na Microsoft, e tokens guardados só para o utilizador."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
MICROSOFT_SCOPES = ["Calendars.ReadWrite", "Mail.Read", "Mail.Send"]
MICROSOFT_AUTHORITY = "https://login.microsoftonline.com/common"


def write_private(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _load_google(path: Path) -> Any:
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(str(path), GOOGLE_SCOPES)


class GoogleTokenSource:
    def __init__(self, path: Path, loader: Callable[[Path], Any] = _load_google) -> None:
        self._path = Path(path)
        self._creds = loader(self._path)
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            if not self._creds.valid:
                from google.auth.transport.requests import Request

                await asyncio.to_thread(self._creds.refresh, Request())
                write_private(self._path, self._creds.to_json())
            return self._creds.token


def connect_google(client_secret: Path, token_path: Path) -> None:
    """Abre o browser para o login Google (corre uma vez, no PC)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0)
    write_private(token_path, creds.to_json())


def microsoft_app(client_id: str, cache_path: Path) -> tuple[Any, Any]:
    import msal

    cache = msal.SerializableTokenCache()
    if Path(cache_path).exists():
        cache.deserialize(Path(cache_path).read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(client_id, authority=MICROSOFT_AUTHORITY, token_cache=cache)
    return app, cache


class MicrosoftTokenSource:
    def __init__(self, app: Any, cache: Any, cache_path: Path) -> None:
        self._app, self._cache, self._path = app, cache, Path(cache_path)
        self._lock = asyncio.Lock()

    def _acquire(self) -> dict | None:
        accounts = self._app.get_accounts()
        if not accounts:
            return None
        return self._app.acquire_token_silent(MICROSOFT_SCOPES, account=accounts[0])

    async def get_token(self) -> str:
        async with self._lock:
            result = await asyncio.to_thread(self._acquire)
            if self._cache.has_state_changed:
                write_private(self._path, self._cache.serialize())
            if not result or "access_token" not in result:
                raise RuntimeError(
                    "Sessão Microsoft expirada: corre `python -m friday connect microsoft`."
                )
            return result["access_token"]


def connect_microsoft(client_id: str, cache_path: Path) -> None:
    """Login por código (abre https://microsoft.com/devicelogin noutro dispositivo ou no PC)."""
    app, cache = microsoft_app(client_id, cache_path)
    flow = app.initiate_device_flow(scopes=MICROSOFT_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Não foi possível iniciar o login: {flow}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Login falhou: {result.get('error_description', result)}")
    write_private(cache_path, cache.serialize())
