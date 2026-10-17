from zoneinfo import ZoneInfo

import pytest

LISBON = ZoneInfo("Europe/Lisbon")


class StaticToken:
    async def get_token(self) -> str:
        return "tok"


@pytest.fixture
def token():
    return StaticToken()
