import base64
import email
import email.policy
import json

import httpx
import respx

from friday.integrations.gmail import Gmail

from .conftest import LISBON

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _meta(mid, sender, subject, snippet, ts):
    return {
        "id": mid,
        "threadId": "t" + mid,
        "snippet": snippet,
        "labelIds": ["UNREAD", "INBOX", "IMPORTANT"],
        "internalDate": str(ts),
        "payload": {
            "headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]
        },
    }


@respx.mock
async def test_inbox_lists_unread_important(token):
    lst = respx.get(f"{BASE}/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "m1"}]})
    )
    respx.get(f"{BASE}/messages/m1").mock(
        return_value=httpx.Response(
            200, json=_meta("m1", "João <joao@x.pt>", "Reunião", "Confirmas?", 1792224000000)
        )
    )
    mails = await Gmail(token, LISBON).inbox(limit=5)
    assert "is:unread" in lst.calls[0].request.url.params["q"]
    assert lst.calls[0].request.url.params["maxResults"] == "5"
    [m] = mails
    assert (m.id, m.sender, m.subject, m.snippet) == (
        "m1",
        "João <joao@x.pt>",
        "Reunião",
        "Confirmas?",
    )
    assert m.unread and m.important and m.provider == "google"


@respx.mock
async def test_read_returns_plain_text_body(token):
    body = base64.urlsafe_b64encode("Olá Fábio,\nchego às 15h.".encode()).decode().rstrip("=")
    respx.get(f"{BASE}/messages/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                **_meta("m1", "João <joao@x.pt>", "Hora", "chego", 1792224000000),
                "payload": {
                    "headers": [
                        {"name": "From", "value": "João <joao@x.pt>"},
                        {"name": "Subject", "value": "Hora"},
                    ],
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": body}},
                        {"mimeType": "text/html", "body": {"data": "PGI-aWdub3JlPC9iPg"}},
                    ],
                },
            },
        )
    )
    text = await Gmail(token, LISBON).read("m1")
    assert "chego às 15h." in text and "<b>" not in text


@respx.mock
async def test_send_builds_mime(token):
    route = respx.post(f"{BASE}/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "s1"})
    )
    await Gmail(token, LISBON).send("joao@x.pt", "Atraso", "Chego às 15h.")
    raw = json.loads(route.calls[0].request.content)["raw"]
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert msg["To"] == "joao@x.pt" and msg["Subject"] == "Atraso"
    assert msg.get_payload(decode=True).decode().strip() == "Chego às 15h."


@respx.mock
async def test_reply_keeps_thread(token):
    respx.get(f"{BASE}/messages/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "João <joao@x.pt>"},
                        {"name": "Subject", "value": "Hora"},
                        {"name": "Message-ID", "value": "<abc@mail>"},
                    ]
                },
            },
        )
    )
    route = respx.post(f"{BASE}/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "s2"})
    )
    await Gmail(token, LISBON).reply("m1", "Combinado.")
    sent = json.loads(route.calls[0].request.content)
    assert sent["threadId"] == "t1"
    msg = email.message_from_bytes(
        base64.urlsafe_b64decode(sent["raw"] + "=" * (-len(sent["raw"]) % 4)),
        policy=email.policy.default,
    )
    assert msg["To"] == "João <joao@x.pt>" and msg["Subject"] == "Re: Hora"
    assert msg["In-Reply-To"] == "<abc@mail>"
