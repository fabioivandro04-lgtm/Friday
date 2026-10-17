"""Registo de ferramentas que a Friday pode usar via function calling."""

from __future__ import annotations

import inspect
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
    summary: Callable[[dict[str, Any]], str | Awaitable[str]] | None = None
    # Valida os argumentos antes de pedir confirmação; devolve a mensagem de erro ou None.
    validate: Callable[[dict[str, Any]], str | None] | None = None


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
    try:
        problem = tool.validate(args) if tool.validate else None
    except Exception as e:  # argumentos com tipos errados vindos do LLM
        problem = f"argumentos inválidos ({e})"
    if problem:
        return f"ERRO: {problem}"
    if tool.mutating:
        if confirmations.pending() is not None:
            return "ERRO: já há uma ação à espera de confirmação; trata uma de cada vez."
        try:
            summary = tool.summary(args) if tool.summary else f"Executar {tool.name}"
            if inspect.isawaitable(summary):
                summary = await summary
        except Exception as e:
            return f"ERRO: {e}"
        action = confirmations.propose(tool, args, summary=summary)
        return f"PENDENTE: {action.summary}. Pergunta ao utilizador se confirma."
    try:
        return await tool.handler(**args)
    except Exception as e:  # o LLM recebe o erro e explica-o em vez de a conversa parar
        return f"ERRO: {e}"
