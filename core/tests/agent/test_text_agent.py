from friday.agent.text_agent import TextAgent, guess_language, strip_thinking
from friday.config import Config, TtsConfig
from friday.tools.registry import Tool, ToolRegistry


class FakeMemory:
    def __init__(self):
        self.turns = []

    def context_for(self, q):
        return "O Fábio prefere reuniões de manhã."

    def log_turn(self, role, text):
        self.turns.append((role, text))


class FakeClient:
    """Devolve respostas programadas e guarda o que recebeu."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append(([dict(m) for m in messages], tools))
        return self.replies.pop(0)


def _agent(client, sent=None):
    sent = sent if sent is not None else []

    async def agenda(day="hoje"):
        return "- 10:00 Reunião"

    async def send(to):
        sent.append(to)
        return f"enviado a {to}"

    reg = ToolRegistry()
    reg.register(Tool("agenda", "Agenda", {"type": "object", "properties": {}}, agenda))
    reg.register(
        Tool(
            "send",
            "Envia",
            {"type": "object", "properties": {}},
            send,
            mutating=True,
            summary=lambda a: f"Enviar a {a['to']}",
        )
    )
    cfg = Config(tts=TtsConfig("pt_PT-x", "en_GB-x"))
    return TextAgent(cfg, reg, FakeMemory(), client), sent


def _text(content):
    return {"content": content, "tool_calls": []}


def _call(name, args, id_="c1"):
    return {"content": None, "tool_calls": [{"id": id_, "name": name, "arguments": args}]}


async def test_plain_reply_with_prompt_and_memory():
    client = FakeClient(_text("Olá, Fábio."))
    agent, _ = _agent(client)
    assert await agent.reply("chat1", "olá") == "Olá, Fábio."
    system = client.calls[0][0][0]
    assert system["role"] == "system" and "reuniões de manhã" in system["content"]
    assert "mensagem escrita" in system["content"]
    assert agent._memory.turns == [("user", "olá"), ("assistant", "Olá, Fábio.")]


async def test_tool_loop():
    client = FakeClient(_call("agenda", {"day": "hoje"}), _text("Tens uma reunião às 10h."))
    agent, _ = _agent(client)
    assert await agent.reply("c", "o que tenho hoje?") == "Tens uma reunião às 10h."
    second = client.calls[1][0]
    tool_msg = second[-1]
    assert tool_msg["role"] == "tool" and tool_msg["content"] == "- 10:00 Reunião"
    assert second[-2]["tool_calls"][0]["function"]["name"] == "agenda"


async def test_history_is_kept_per_conversation():
    client = FakeClient(_text("a"), _text("b"), _text("c"))
    agent, _ = _agent(client)
    await agent.reply("x", "um")
    await agent.reply("y", "outro")
    await agent.reply("x", "dois")
    roles = [m["content"] for m in client.calls[2][0] if m["role"] == "user"]
    assert roles == ["um", "dois"]


async def test_mutating_tool_waits_for_yes():
    client = FakeClient(_call("send", {"to": "João"}), _text("Queres que envie ao João?"))
    agent, sent = _agent(client)
    assert await agent.reply("c", "envia ao João") == "Queres que envie ao João?"
    assert sent == []
    assert await agent.reply("c", "sim") == "Feito: enviado a João"
    assert sent == ["João"]


async def test_other_message_cancels_pending():
    client = FakeClient(_call("send", {"to": "João"}), _text("Confirmas?"), _text("Está sol."))
    agent, sent = _agent(client)
    await agent.reply("c", "envia ao João")
    assert await agent.reply("c", "como está o tempo hoje?") == "Está sol."
    assert sent == [] and agent.pending("c") is None


async def test_no_cancels():
    client = FakeClient(_call("send", {"to": "João"}), _text("Confirmas?"))
    agent, sent = _agent(client)
    await agent.reply("c", "envia ao João")
    assert await agent.reply("c", "não") == "Cancelado."
    assert sent == []


async def test_thinking_is_stripped_and_loops_are_bounded():
    client = FakeClient(_text("<think>hmm</think>Olá!"))
    agent, _ = _agent(client)
    assert await agent.reply("c", "olá") == "Olá!"
    looping = FakeClient(*[_call("agenda", {}, id_=str(i)) for i in range(10)])
    agent2, _ = _agent(looping)
    out = await agent2.reply("c", "loop")
    assert "não consegui" in out.lower()
    assert len(looping.calls) <= 6


async def test_llm_failure_becomes_message():
    class Broken:
        async def complete(self, messages, tools):
            raise ConnectionError("ollama em baixo")

    agent, _ = _agent(Broken())
    assert "modelo" in (await agent.reply("c", "olá")).lower()


def test_strip_thinking():
    assert strip_thinking("<think>\na\n</think>\n\nResposta") == "Resposta"


def test_guess_language():
    assert guess_language("what is the weather like tomorrow?", "pt") == "en"
    assert guess_language("que tempo vai fazer amanhã?", "en") == "pt"
    assert guess_language("ok", "en") == "en"
