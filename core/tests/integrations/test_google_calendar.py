import json
from datetime import date, datetime

import httpx
import respx

from friday.integrations.google_calendar import GoogleCalendar

from .conftest import LISBON

URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


@respx.mock
async def test_list_events_for_a_day(token):
    route = respx.get(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "e1",
                        "summary": "Reunião de equipa",
                        "start": {"dateTime": "2026-10-17T10:00:00+01:00"},
                        "end": {"dateTime": "2026-10-17T11:00:00+01:00"},
                        "location": "Escritório",
                    },
                    {
                        "id": "e2",
                        "summary": "Feriado",
                        "start": {"date": "2026-10-17"},
                        "end": {"date": "2026-10-18"},
                    },
                ]
            },
        )
    )
    events = await GoogleCalendar(token, LISBON).list_events(date(2026, 10, 17))
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer tok"
    assert req.url.params["singleEvents"] == "true"
    assert req.url.params["timeMin"].startswith("2026-10-17T00:00:00")
    assert [e.title for e in events] == ["Reunião de equipa", "Feriado"]
    assert events[0].start == datetime(2026, 10, 17, 10, 0, tzinfo=LISBON)
    assert events[0].location == "Escritório" and events[0].provider == "google"
    assert events[1].all_day is True


@respx.mock
async def test_create_event(token):
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "new",
                "summary": "Café com o João",
                "start": {"dateTime": "2026-10-18T15:00:00+01:00"},
                "end": {"dateTime": "2026-10-18T15:30:00+01:00"},
            },
        )
    )
    start = datetime(2026, 10, 18, 15, 0, tzinfo=LISBON)
    end = datetime(2026, 10, 18, 15, 30, tzinfo=LISBON)
    ev = await GoogleCalendar(token, LISBON).create_event(
        "Café com o João", start, end, ["joao@x.pt"]
    )
    body = json.loads(route.calls[0].request.content)
    assert body["summary"] == "Café com o João"
    assert body["start"] == {"dateTime": "2026-10-18T15:00:00+01:00", "timeZone": "Europe/Lisbon"}
    assert body["attendees"] == [{"email": "joao@x.pt"}]
    assert ev.id == "new"
