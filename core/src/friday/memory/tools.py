"""Ferramentas para a Friday guardar e recuperar factos da sua memória."""

from __future__ import annotations

from friday.memory.store import MemoryStore
from friday.tools.registry import Tool


def make_memory_tools(store: MemoryStore) -> list[Tool]:
    async def remember(fact: str) -> str:
        return "Guardado." if store.add_fact(fact) else "Já sabia."

    async def recall(query: str) -> str:
        facts = store.search(query)
        return "\n".join(facts) if facts else "Não tenho nada guardado sobre isso."

    return [
        Tool(
            name="remember",
            description="Guarda um facto duradouro sobre o utilizador (preferências, rotinas).",
            parameters={
                "type": "object",
                "properties": {"fact": {"type": "string", "description": "O facto, numa frase"}},
                "required": ["fact"],
            },
            handler=remember,
        ),
        Tool(
            name="recall",
            description="Procura na memória factos guardados sobre um tema.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=recall,
        ),
    ]
