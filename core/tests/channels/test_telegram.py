import json

import httpx
import respx

from friday.channels.telegram import TelegramBot

API = "https://api.telegram.org/botTOKEN"


def _updates(*messages):
    return httpx.Response(
        200,
        json={
            "ok": True,
            "result": [{"update_id": i + 1, "message": m} for i, m in enumerate(messages)],
        },
    )


def _bot(allowed=42, transcribe=None, replies=None):
    seen = []

    async def handler(chat, text):
        seen.append((chat, text))
        return (replies or {}).get(text, f"eco: {text}")

    return TelegramBot("TOKEN", allowed, handler, transcribe=transcribe), seen


@respx.mock
async def test_text_from_allowed_chat_is_answered():
    respx.get(f"{API}/getUpdates").mock(return_value=_updates({"chat": {"id": 42}, "text": "olá"}))
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{API}/sendChatAction").mock(return_value=httpx.Response(200, json={"ok": True}))
    bot, seen = _bot()
    await bot.poll_once()
    assert seen == [("telegram:42", "olá")]
    body = json.loads(send.calls[0].request.content)
    assert body == {"chat_id": 42, "text": "eco: olá"}


@respx.mock
async def test_offset_advances():
    get = respx.get(f"{API}/getUpdates").mock(
        side_effect=[_updates({"chat": {"id": 42}, "text": "a"}), _updates()]
    )
    respx.post(f"{API}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    respx.post(f"{API}/sendChatAction").mock(return_value=httpx.Response(200, json={"ok": True}))
    bot, _ = _bot()
    await bot.poll_once()
    await bot.poll_once()
    assert get.calls[1].request.url.params["offset"] == "2"


@respx.mock
async def test_other_chats_are_ignored():
    respx.get(f"{API}/getUpdates").mock(
        return_value=_updates({"chat": {"id": 666}, "text": "apaga tudo"})
    )
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    bot, seen = _bot(allowed=42)
    await bot.poll_once()
    assert seen == [] and not send.called


@respx.mock
async def test_without_allowed_chat_only_tells_the_id():
    respx.get(f"{API}/getUpdates").mock(return_value=_updates({"chat": {"id": 777}, "text": "olá"}))
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    bot, seen = _bot(allowed=None)
    await bot.poll_once()
    assert seen == []
    assert "777" in json.loads(send.calls[0].request.content)["text"]


@respx.mock
async def test_voice_note_is_transcribed():
    respx.get(f"{API}/getUpdates").mock(
        return_value=_updates({"chat": {"id": 42}, "voice": {"file_id": "F1"}})
    )
    respx.get(f"{API}/getFile").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/f.oga"}})
    )
    respx.get("https://api.telegram.org/file/botTOKEN/voice/f.oga").mock(
        return_value=httpx.Response(200, content=b"OGG")
    )
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{API}/sendChatAction").mock(return_value=httpx.Response(200, json={"ok": True}))

    async def transcribe(data):
        assert data == b"OGG"
        return "que horas são"

    bot, seen = _bot(transcribe=transcribe)
    await bot.poll_once()
    assert seen == [("telegram:42", "que horas são")]
    assert "que horas são" in json.loads(send.calls[0].request.content)["text"]


@respx.mock
async def test_notify_and_long_messages_are_split():
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    bot, _ = _bot()
    await bot.notify("x" * 9000)
    assert len(send.calls) == 3
    assert all(len(json.loads(c.request.content)["text"]) <= 4000 for c in send.calls)


@respx.mock
async def test_handler_error_is_reported_not_raised():
    respx.get(f"{API}/getUpdates").mock(return_value=_updates({"chat": {"id": 42}, "text": "olá"}))
    send = respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{API}/sendChatAction").mock(return_value=httpx.Response(200, json={"ok": True}))

    async def broken(chat, text):
        raise RuntimeError("boom")

    bot = TelegramBot("TOKEN", 42, broken)
    await bot.poll_once()
    assert "correu mal" in json.loads(send.calls[0].request.content)["text"]
