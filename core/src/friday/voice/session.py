"""Uma sessão de voz de cada vez: um novo dispositivo substitui o anterior.

Evita dois Whisper na VRAM e ações pendentes partilhadas entre o PC e o telemóvel.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

Stop = Callable[[], Awaitable[None] | None]


class SessionSlot:
    def __init__(self) -> None:
        self._holder = 0
        self._stop: Stop | None = None

    async def claim(self, stop: Stop) -> int:
        previous, self._stop = self._stop, stop
        self._holder += 1
        if previous is not None:
            result = previous()
            if inspect.isawaitable(result):
                await result
        return self._holder

    def release(self, holder: int) -> None:
        if holder == self._holder:
            self._stop = None
