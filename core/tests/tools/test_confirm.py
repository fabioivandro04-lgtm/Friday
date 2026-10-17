import pytest

from friday.tools.confirm import ConfirmationManager, parse_confirmation
from friday.tools.registry import Tool


async def _noop() -> str:
    return "ok"


SEND = Tool(name="send", description="", parameters={}, handler=_noop, mutating=True)


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("sim", "confirmed"),
        ("Sim, envia", "confirmed"),
        ("yes", "confirmed"),
        ("confirmo", "confirmed"),
        ("não", "rejected"),
        ("Não, cancela.", "rejected"),
        ("no", "rejected"),
        ("talvez", "unclear"),
        ("não sei", "unclear"),
        ("", "unclear"),
        ("o tempo amanhã", "unclear"),
    ],
)
def test_parse_confirmation(answer, expected):
    assert parse_confirmation(answer) == expected


def test_pending_action_expires():
    t = [0.0]
    conf = ConfirmationManager(ttl_s=60, clock=lambda: t[0])
    conf.propose(SEND, {})
    t[0] = 61
    assert conf.pending() is None


def test_cancel_on_interrupt_never_executes():
    conf = ConfirmationManager()
    action = conf.propose(SEND, {})
    conf.cancel()
    assert conf.pending() is None
    assert conf.confirm_by_id(action.id) is None


def test_confirm_by_id_returns_and_clears():
    conf = ConfirmationManager()
    action = conf.propose(SEND, {"to": "x"})
    assert conf.confirm_by_id(action.id) is action
    assert conf.pending() is None


def test_resolve_confirmed_clears_and_unclear_keeps():
    conf = ConfirmationManager()
    conf.propose(SEND, {})
    assert conf.resolve("talvez") == "unclear"
    assert conf.pending() is not None
    assert conf.resolve("não") == "rejected"
    assert conf.pending() is None


def test_new_proposal_replaces_old():
    conf = ConfirmationManager()
    first = conf.propose(SEND, {"n": 1})
    conf.propose(SEND, {"n": 2})
    assert conf.confirm_by_id(first.id) is None
    assert conf.pending().args == {"n": 2}
