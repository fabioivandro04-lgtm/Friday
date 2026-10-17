"""Registo de ferramentas que a Friday pode usar via function calling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from friday.tools.confirm import ConfirmationManager


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[str]]
    # Ferramentas que alteram algo (enviar, apagar, marcar) exigem confirmação.
    mutating: bool = False
    # Texto do cartão de confirmação, a partir dos argumentos.
    summary: Callable[[dict[str, Any]], str] | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"ferramenta repetida: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]


async def execute(
    registry: ToolRegistry,
    confirmations: ConfirmationManager,
    name: str,
    args: dict[str, Any],
) -> str:
    try:
        tool = registry.get(name)
    except KeyError:
        return f"ERRO: ferramenta desconhecida: {name}"
    if tool.mutating:
        action = confirmations.propose(tool, args)
        return f"PENDENTE: {action.summary}. Pergunta ao utilizador se confirma."
    return await tool.handler(**args)
