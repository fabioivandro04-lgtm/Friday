import base64
import hashlib
import hmac
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from friday.channels.twilio import OneTimeTokens, TwilioCaller, twiml_stream, validate_signature
from friday.config import TwilioConfig

URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
PARAMS = {
    "CallSid": "CA1234567890ABCDE",
    "Caller": "+12349013030",
    "Digits": "1234",
    "From": "+12349013030",
    "To": "+18005551212",
}


def _reference_signature(url, params, token):
    # Algoritmo documentado pela Twilio: URL + chaves ordenadas com os valores, HMAC-SHA1, base64.
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


def test_valid_signature_accepted_and_tampering_rejected():
    sig = _reference_signature(URL, PARAMS, "12345")
    assert validate_signature(URL, PARAMS, sig, "12345")
    assert not validate_signature(URL, {**PARAMS, "To": "+1999"}, sig, "12345")
    assert not validate_signature(URL, PARAMS, sig, "outro-token")
    assert not validate_signature(URL, PARAMS, "", "12345")


def test_one_time_tokens():
    t = [0.0]
    tokens = OneTimeTokens(ttl_s=300, clock=lambda: t[0])
    a = tokens.issue({"greeting": "Bom dia"})
    assert tokens.peek(a) == {"greeting": "Bom dia"}
    assert tokens.consume(a) == {"greeting": "Bom dia"}
    assert tokens.consume(a) is None
    b = tokens.issue({})
    t[0] = 301
    assert tokens.peek(b) is None


def test_twiml_stream():
    xml = twiml_stream("wss://pc.ts.net/twilio/ws?t=abc&x=1")
    assert (
        xml.startswith("<?xml")
        and '<Connect><Stream url="wss://pc.ts.net/twilio/ws?t=abc&amp;x=1" />' in xml
    )


CFG = TwilioConfig(
    enabled=True,
    account_sid="AC123",
    from_number="+351210000000",
    to_number="+351910000000",
    public_url="https://pc.tail1234.ts.net",
    auth_token="secret",
)


@respx.mock
async def test_place_call_only_to_configured_number():
    route = respx.post("https://api.twilio.com/2010-04-01/Accounts/AC123/Calls.json").mock(
        return_value=httpx.Response(201, json={"sid": "CA1"})
    )
    tokens = OneTimeTokens()
    sid = await TwilioCaller(CFG, tokens).call("Bom dia, Fábio.")
    assert sid == "CA1"
    req = route.calls[0].request
    form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
    assert form["To"] == "+351910000000" and form["From"] == "+351210000000"
    assert form["Url"].startswith("https://pc.tail1234.ts.net/twilio/voice?t=")
    token = form["Url"].split("t=")[1]
    assert tokens.peek(token) == {"greeting": "Bom dia, Fábio."}
    assert req.headers["authorization"] == "Basic " + base64.b64encode(b"AC123:secret").decode()


async def test_call_refuses_incomplete_config():
    with pytest.raises(ValueError, match="Twilio: falta"):
        await TwilioCaller(
            TwilioConfig(enabled=True, account_sid="AC1", auth_token="x"), OneTimeTokens()
        ).call("x")
