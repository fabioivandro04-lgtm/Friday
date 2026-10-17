"""Pedidos HTTP autenticados (Bearer) partilhados pelos clientes."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from friday.integrations.models import TokenSource

TIMEOUT = httpx.Timeout(15.0)


async def request(
    token: TokenSource, method: str, url: str, *, headers: dict | None = None, **kwargs: Any
) -> httpx.Response:
    auth = {"Authorization": f"Bearer {await token.get_token()}", **(headers or {})}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.request(method, url, headers=auth, **kwargs)
    response.raise_for_status()
    return response


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)
