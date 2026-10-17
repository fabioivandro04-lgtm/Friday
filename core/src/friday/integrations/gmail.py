"""Gmail (API v1): caixa de entrada, leitura, envio e resposta."""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from email.message import EmailMessage
from html import unescape
from zoneinfo import ZoneInfo

from friday.integrations._http import request
from friday.integrations.models import MailSummary, TokenSource

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_INBOX_QUERY = "is:unread in:inbox category:primary"


def _headers(payload: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _b64decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _find(payload: dict, mime: str) -> str:
    if payload.get("mimeType", "").startswith(mime) and payload.get("body", {}).get("data"):
        return _b64decode(payload["body"]["data"])
    for part in payload.get("parts", []):
        text = _find(part, mime)
        if text:
            return text
    return ""


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", "", html)).strip()


def _plain_text(payload: dict) -> str:
    # Muitos emails (newsletters, faturas) só têm HTML.
    return _find(payload, "text/plain") or _strip_html(_find(payload, "text/html"))


def _raw(msg: EmailMessage) -> str:
    return base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")


class Gmail:
    name = "google"

    def __init__(self, token: TokenSource, tz: ZoneInfo) -> None:
        self._token = token
        self._tz = tz

    async def _get(self, message_id: str, fmt: str) -> dict:
        params = {"format": fmt}
        if fmt == "metadata":
            # A API só devolve os cabeçalhos pedidos.
            params["metadataHeaders"] = ["From", "Subject", "Message-ID", "Reply-To", "References"]
        return (
            await request(self._token, "GET", f"{BASE}/messages/{message_id}", params=params)
        ).json()

    async def inbox(self, limit: int = 5) -> list[MailSummary]:
        params = {"q": _INBOX_QUERY, "maxResults": str(limit)}
        listing = (await request(self._token, "GET", f"{BASE}/messages", params=params)).json()
        out = []
        for ref in listing.get("messages", []):
            m = await self._get(ref["id"], "metadata")
            h = _headers(m.get("payload", {}))
            labels = m.get("labelIds", [])
            out.append(
                MailSummary(
                    id=m["id"],
                    sender=h.get("from", ""),
                    subject=h.get("subject", "(sem assunto)"),
                    snippet=m.get("snippet", ""),
                    received=datetime.fromtimestamp(
                        int(m.get("internalDate", "0")) / 1000, UTC
                    ).astimezone(self._tz),
                    provider="google",
                    unread="UNREAD" in labels,
                    important="IMPORTANT" in labels,
                )
            )
        return out

    async def read(self, message_id: str) -> str:
        m = await self._get(message_id, "full")
        h = _headers(m.get("payload", {}))
        body = _plain_text(m.get("payload", {}))
        return f"De: {h.get('from', '')}\nAssunto: {h.get('subject', '')}\n\n{body}"

    async def describe(self, message_id: str) -> tuple[str, str]:
        h = _headers((await self._get(message_id, "metadata")).get("payload", {}))
        return h.get("reply-to") or h.get("from", ""), h.get("subject", "")

    async def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        msg.set_content(body)
        await request(self._token, "POST", f"{BASE}/messages/send", json={"raw": _raw(msg)})

    async def reply(self, message_id: str, body: str) -> None:
        original = await self._get(message_id, "metadata")
        h = _headers(original.get("payload", {}))
        subject = h.get("subject", "")
        msg = EmailMessage()
        msg["To"] = h.get("reply-to") or h.get("from", "")
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if h.get("message-id"):
            msg["In-Reply-To"] = h["message-id"]
            msg["References"] = " ".join(x for x in (h.get("references"), h["message-id"]) if x)
        msg.set_content(body)
        payload = {"raw": _raw(msg), "threadId": original.get("threadId")}
        await request(self._token, "POST", f"{BASE}/messages/send", json=payload)
