"""Google Calendar (API v3)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from friday.integrations._http import day_bounds, request
from friday.integrations.models import CalendarEvent, TokenSource

URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _parse_time(value: dict, tz: ZoneInfo) -> tuple[datetime, bool]:
    if "dateTime" in value:
        return datetime.fromisoformat(value["dateTime"]).astimezone(tz), False
    return datetime.combine(date.fromisoformat(value["date"]), datetime.min.time(), tzinfo=tz), True


def _event(item: dict, tz: ZoneInfo) -> CalendarEvent:
    start, all_day = _parse_time(item["start"], tz)
    end, _ = _parse_time(item["end"], tz)
    return CalendarEvent(
        id=item["id"],
        title=item.get("summary", "(sem título)"),
        start=start,
        end=end,
        provider="google",
        location=item.get("location", ""),
        all_day=all_day,
    )


class GoogleCalendar:
    name = "google"

    def __init__(self, token: TokenSource, tz: ZoneInfo) -> None:
        self._token = token
        self._tz = tz

    async def list_events(self, day: date) -> list[CalendarEvent]:
        start, end = day_bounds(day, self._tz)
        params = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "50",
        }
        data = (await request(self._token, "GET", URL, params=params)).json()
        return [_event(item, self._tz) for item in data.get("items", [])]

    async def create_event(
        self, title: str, start: datetime, end: datetime, attendees: list[str]
    ) -> CalendarEvent:
        zone = str(self._tz)
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": zone},
            "end": {"dateTime": end.isoformat(), "timeZone": zone},
        }
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        data = (await request(self._token, "POST", URL, json=body)).json()
        return _event(data, self._tz)
