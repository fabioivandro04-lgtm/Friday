import time

from friday.tools.web_search import make_web_search_tool

ERRO = "ERRO: a pesquisa não está disponível neste momento."


async def test_formats_results():
    tool = make_web_search_tool(
        search=lambda q, n: [{"title": "T", "body": "B", "href": "https://x"}]
    )
    out = await tool.handler(query="tempo Lisboa")
    assert out == "- T: B (https://x)"
    assert tool.name == "web_search" and tool.mutating is False


async def test_passes_query_and_limits_to_five():
    seen = {}

    def search(q, n):
        seen["q"], seen["n"] = q, n
        return [{"title": str(i), "body": "", "href": ""} for i in range(9)]

    out = await make_web_search_tool(search=search).handler(query="q")
    assert seen == {"q": "q", "n": 5}
    assert out.count("\n") == 4


async def test_truncates_long_results():
    big = [{"title": "T", "body": "x" * 10_000, "href": "h"}]
    out = await make_web_search_tool(search=lambda q, n: big, max_chars=1500).handler(query="q")
    assert len(out) <= 1500


async def test_failure_becomes_message():
    def boom(q, n):
        raise RuntimeError("rede")

    assert await make_web_search_tool(search=boom).handler(query="q") == ERRO


async def test_timeout_becomes_message():
    def slow(q, n):
        time.sleep(1)
        return []

    assert await make_web_search_tool(search=slow, timeout_s=0.05).handler(query="q") == ERRO


async def test_no_results_message():
    out = await make_web_search_tool(search=lambda q, n: []).handler(query="q")
    assert out == "Sem resultados."
