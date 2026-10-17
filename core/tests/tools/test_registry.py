import pytest

from friday.tools.confirm import ConfirmationManager
from friday.tools.registry import Tool, ToolRegistry, execute


async def _echo(text: str) -> str:
    return f"eco: {text}"


def _echo_tool() -> Tool:
    params = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    return Tool(name="echo", description="Repete", parameters=params, handler=_echo)


def _send_tool(sent: list) -> Tool:
    async def send(to: str) -> str:
        sent.append(to)
        return "enviado"

    return Tool(
        name="send",
        description="Envia",
        parameters={"type": "object", "properties": {"to": {"type": "string"}}},
        handler=send,
        mutating=True,
        summary=lambda args: f"Enviar mensagem a {args['to']}",
    )


def test_schemas_use_openai_function_format():
    reg = ToolRegistry()
    reg.register(_echo_tool())
    [schema] = reg.schemas()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert schema["function"]["parameters"]["required"] == ["text"]


def test_duplicate_tool_name_rejected():
    reg = ToolRegistry()
    reg.register(_echo_tool())
    with pytest.raises(ValueError, match="echo"):
        reg.register(_echo_tool())


async def test_read_only_tool_runs_immediately():
    reg, conf = ToolRegistry(), ConfirmationManager()
    reg.register(_echo_tool())
    assert await execute(reg, conf, "echo", {"text": "oi"}) == "eco: oi"
    assert conf.pending() is None


async def test_mutating_tool_requires_confirmation():
    sent: list = []
    reg, conf = ToolRegistry(), ConfirmationManager()
    reg.register(_send_tool(sent))
    result = await execute(reg, conf, "send", {"to": "João"})
    assert result.startswith("PENDENTE: Enviar mensagem a João")
    assert sent == []
    assert conf.pending().tool == "send"


async def test_unknown_tool_returns_error():
    out = await execute(ToolRegistry(), ConfirmationManager(), "nope", {})
    assert out.startswith("ERRO:")


async def test_validate_rejects_before_proposing():
    async def noop(**kw):
        return "ok"

    tool = Tool(
        name="send",
        description="",
        parameters={},
        handler=noop,
        mutating=True,
        validate=lambda args: None if "@" in args.get("to", "") else "email inválido",
    )
    reg, conf = ToolRegistry(), ConfirmationManager()
    reg.register(tool)
    assert await execute(reg, conf, "send", {"to": "x"}) == "ERRO: email inválido"
    assert conf.pending() is None


async def test_handler_exception_becomes_error_message():
    async def boom(**kw):
        raise RuntimeError("rede em baixo")

    reg, conf = ToolRegistry(), ConfirmationManager()
    reg.register(Tool(name="t", description="", parameters={}, handler=boom))
    assert await execute(reg, conf, "t", {}) == "ERRO: rede em baixo"


async def test_async_summary_and_bad_validate_input():
    async def noop(**kw):
        return "ok"

    async def summary(args):
        return f"Responder a {args['who']}"

    def validate(args):
        return None if "@" in args["to"] else "x"  # rebenta se o LLM mandar um número

    reg, conf = ToolRegistry(), ConfirmationManager()
    reg.register(Tool("r", "", {}, noop, mutating=True, summary=summary))
    reg.register(Tool("v", "", {}, noop, mutating=True, validate=validate))
    assert (await execute(reg, conf, "r", {"who": "João"})).startswith("PENDENTE: Responder a João")
    assert (await execute(reg, conf, "v", {"to": 123})).startswith("ERRO:")


async def test_second_mutating_call_is_refused_while_one_is_pending():
    async def noop(**kw):
        return "ok"

    reg, conf = ToolRegistry(), ConfirmationManager()
    reg.register(Tool("send", "", {}, noop, mutating=True, summary=lambda a: f"Enviar {a['n']}"))
    await execute(reg, conf, "send", {"n": 1})
    second = await execute(reg, conf, "send", {"n": 2})
    assert second.startswith("ERRO:") and conf.pending().args == {"n": 1}
