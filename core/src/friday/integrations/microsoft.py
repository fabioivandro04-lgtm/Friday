"""Outlook / Microsoft 365 via Microsoft Graph: calendário e email."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from friday.integrations._http import day_bounds, request
from friday.integrations.models import CalendarEvent, MailSummary, TokenSource

G = "https://graph.microsoft.com/v1.0/me"


def _graph_time(value: dict, tz: ZoneInfo) -> datetime:
    # Graph devolve "2026-10-17T17:00:00.0000000" no fuso pedido em Prefer.
    raw = value["dateTime"].split(".")[0]
    return datetime.fromisoformat(raw).replace(tzinfo=ZoneInfo(value.get("timeZone") or str(tz)))


def _event(item: dict, tz: ZoneInfo) -> CalendarEvent:
    return CalendarEvent(
        id=item["id"],
        title=item.get("subject") or "(sem título)",
        start=_graph_time(item["start"], tz).astimezone(tz),
        end=_graph_time(item["end"], tz).astimezone(tz),
        provider="microsoft",
        location=(item.get("location") or {}).get("displayName", ""),
        all_day=bool(item.get("isAllDay")),
    )


class Outlook:
    name = "microsoft"

    def __init__(self, token: TokenSource, tz: ZoneInfo) -> None:
        self._token = token
        self._tz = tz
        self._prefer_tz = {"Prefer": f'outlook.timezone="{tz}"'}

    async def list_events(self, day: date) -> list[CalendarEvent]:
        start, end = day_bounds(day, self._tz)
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$orderby": "start/dateTime",
            "$top": "50",
        }
        data = (
            await request(
                self._token, "GET", f"{G}/calendarView", params=params, headers=self._prefer_tz
            )
        ).json()
        return [_event(item, self._tz) for item in data.get("value", [])]

    async def create_event(
        self, title: str, start: datetime, end: datetime, attendees: list[str]
    ) -> CalendarEvent:
        zone = str(self._tz)
        body = {
            "subject": title,
            "start": {
                "dateTime": start.astimezone(self._tz).replace(tzinfo=None).isoformat(),
                "timeZone": zone,
            },
            "end": {
                "dateTime": end.astimezone(self._tz).replace(tzinfo=None).isoformat(),
                "timeZone": zone,
            },
            "attendees": [{"emailAddress": {"address": a}, "type": "required"} for a in attendees],
        }
        data = (
            await request(self._token, "POST", f"{G}/events", json=body, headers=self._prefer_tz)
        ).json()
        return _event(data, self._tz)

    async def inbox(self, limit: int = 5) -> list[MailSummary]:
        params = {
            "$top": str(limit * 4),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,bodyPreview,receivedDateTime,isRead,importance",
        }
        data = (
            await request(self._token, "GET", f"{G}/mailFolders/inbox/messages", params=params)
        ).json()
        out = []
        for m in data.get("value", []):
            if m.get("isRead"):
                continue
            sender = (m.get("from") or {}).get("emailAddress", {})
            out.append(
                MailSummary(
                    id=m["id"],
                    sender=f"{sender.get('name', '')} <{sender.get('address', '')}>".strip(),
                    subject=m.get("subject") or "(sem assunto)",
                    snippet=m.get("bodyPreview", ""),
                    received=datetime.fromisoformat(
                        m["receivedDateTime"].replace("Z", "+00:00")
                    ).astimezone(self._tz),
                    provider="microsoft",
                    unread=True,
                    important=m.get("importance") == "high",
                )
            )
        return out[:limit]

    async def read(self, message_id: str) -> str:
        headers = {"Prefer": 'outlook.body-content-type="text"'}
        params = {"$select": "subject,from,body"}
        m = (
            await request(
                self._token, "GET", f"{G}/messages/{message_id}", params=params, headers=headers
            )
        ).json()
        sender = (m.get("from") or {}).get("emailAddress", {})
        return (
            f"De: {sender.get('name', '')} <{sender.get('address', '')}>\n"
            f"Assunto: {m.get('subject', '')}\n\n"
            f"{(m.get('body') or {}).get('content', '')}"
        )

    async def send(self, to: str, subject: str, body: str) -> None:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }
        await request(self._token, "POST", f"{G}/sendMail", json=payload)

    async def reply(self, message_id: str, body: str) -> None:
        await request(
            self._token, "POST", f"{G}/messages/{message_id}/reply", json={"comment": body}
        )
