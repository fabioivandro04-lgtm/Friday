import json
from datetime import date, datetime

import httpx
import respx

from friday.integrations.microsoft import Outlook

from .conftest import LISBON

G = "https://graph.microsoft.com/v1.0/me"


@respx.mock
async def test_calendar_view(token):
    route = respx.get(f"{G}/calendarView").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "o1",
                        "subject": "Chamada com cliente",
                        "start": {
                            "dateTime": "2026-10-17T17:00:00.0000000",
                            "timeZone": "Europe/Lisbon",
                        },
                        "end": {
                            "dateTime": "2026-10-17T17:30:00.0000000",
                            "timeZone": "Europe/Lisbon",
                        },
                        "location": {"displayName": "Teams"},
                        "isAllDay": False,
                    }
                ]
            },
        )
    )
    [ev] = await Outlook(token, LISBON).list_events(date(2026, 10, 17))
    req = route.calls[0].request
    assert 'outlook.timezone="Europe/Lisbon"' in req.headers["prefer"]
    assert ev.title == "Chamada com cliente" and ev.provider == "microsoft"
    assert ev.start == datetime(2026, 10, 17, 17, 0, tzinfo=LISBON)


@respx.mock
async def test_create_event(token):
    route = respx.post(f"{G}/events").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "o2",
                "subject": "Almoço",
                "start": {"dateTime": "2026-10-18T13:00:00.0000000", "timeZone": "Europe/Lisbon"},
                "end": {"dateTime": "2026-10-18T14:00:00.0000000", "timeZone": "Europe/Lisbon"},
            },
        )
    )
    ev = await Outlook(token, LISBON).create_event(
        "Almoço",
        datetime(2026, 10, 18, 13, tzinfo=LISBON),
        datetime(2026, 10, 18, 14, tzinfo=LISBON),
        ["ana@x.pt"],
    )
    body = json.loads(route.calls[0].request.content)
    assert body["start"] == {"dateTime": "2026-10-18T13:00:00", "timeZone": "Europe/Lisbon"}
    assert body["attendees"][0]["emailAddress"]["address"] == "ana@x.pt"
    assert ev.id == "o2"


@respx.mock
async def test_inbox_unread_only(token):
    respx.get(f"{G}/mailFolders/inbox/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "x1",
                        "subject": "Fatura",
                        "from": {"emailAddress": {"name": "Banco", "address": "b@banco.pt"}},
                        "bodyPreview": "Segue a fatura",
                        "receivedDateTime": "2026-10-17T08:00:00Z",
                        "isRead": False,
                        "importance": "high",
                    },
                    {
                        "id": "x2",
                        "subject": "Lido",
                        "from": {"emailAddress": {"name": "A", "address": "a@x.pt"}},
                        "bodyPreview": "",
                        "receivedDateTime": "2026-10-17T07:00:00Z",
                        "isRead": True,
                        "importance": "normal",
                    },
                ]
            },
        )
    )
    mails = await Outlook(token, LISBON).inbox(limit=5)
    assert [m.id for m in mails] == ["x1"]
    assert mails[0].sender == "Banco <b@banco.pt>" and mails[0].important


@respx.mock
async def test_send_and_reply(token):
    send = respx.post(f"{G}/sendMail").mock(return_value=httpx.Response(202))
    reply = respx.post(f"{G}/messages/x1/reply").mock(return_value=httpx.Response(202))
    o = Outlook(token, LISBON)
    await o.send("ana@x.pt", "Olá", "Tudo bem?")
    await o.reply("x1", "Obrigado.")
    msg = json.loads(send.calls[0].request.content)["message"]
    assert msg["toRecipients"][0]["emailAddress"]["address"] == "ana@x.pt"
    assert msg["body"] == {"contentType": "Text", "content": "Tudo bem?"}
    assert json.loads(reply.calls[0].request.content) == {"comment": "Obrigado."}


@respx.mock
async def test_read_text_body(token):
    route = respx.get(f"{G}/messages/x1").mock(
        return_value=httpx.Response(
            200, json={"subject": "S", "body": {"contentType": "text", "content": "Olá!"}}
        )
    )
    assert "Olá!" in await Outlook(token, LISBON).read("x1")
    assert 'outlook.body-content-type="text"' in route.calls[0].request.headers["prefer"]


@respx.mock
async def test_unknown_graph_timezone_falls_back(token):
    respx.get(f"{G}/calendarView").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "o1",
                        "subject": "X",
                        "start": {
                            "dateTime": "2026-10-17T17:00:00",
                            "timeZone": "GMT Standard Time",
                        },
                        "end": {"dateTime": "2026-10-17T18:00:00", "timeZone": "GMT Standard Time"},
                    }
                ]
            },
        )
    )
    [ev] = await Outlook(token, LISBON).list_events(date(2026, 10, 17))
    assert ev.start == datetime(2026, 10, 17, 17, 0, tzinfo=LISBON)


@respx.mock
async def test_inbox_asks_graph_for_unread(token):
    route = respx.get(f"{G}/mailFolders/inbox/messages").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await Outlook(token, LISBON).inbox(5)
    assert route.calls[0].request.url.params["$filter"] == "isRead eq false"


@respx.mock
async def test_describe(token):
    respx.get(f"{G}/messages/x1").mock(
        return_value=httpx.Response(
            200, json={"subject": "S", "from": {"emailAddress": {"name": "A", "address": "a@x.pt"}}}
        )
    )
    assert await Outlook(token, LISBON).describe("x1") == ("A <a@x.pt>", "S")
