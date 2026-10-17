"""Pesquisa na internet (DuckDuckGo, sem chave)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from friday.tools.registry import Tool

SearchFn = Callable[[str, int], list[dict]]

_MAX_RESULTS = 5
_ERROR = "ERRO: a pesquisa não está disponível neste momento."


def _ddgs_search(query: str, n: int) -> list[dict]:
    from ddgs import DDGS

    return DDGS().text(query, max_results=n)


def make_web_search_tool(
    search: SearchFn | None = None, max_chars: int = 1500, timeout_s: float = 6.0
) -> Tool:
    search = search or _ddgs_search

    async def handler(query: str) -> str:
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(search, query, _MAX_RESULTS), timeout=timeout_s
            )
        except Exception:
            return _ERROR
        lines = [
            f"- {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})"
            for r in results[:_MAX_RESULTS]
        ]
        return "\n".join(lines)[:max_chars] if lines else "Sem resultados."

    return Tool(
        name="web_search",
        description="Pesquisa na internet informação atual (notícias, tempo, factos).",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "O que pesquisar"}},
            "required": ["query"],
        },
        handler=handler,
    )
