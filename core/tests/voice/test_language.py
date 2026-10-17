import pytest

from friday.voice.language import choose_language


@pytest.mark.parametrize(
    "detected,prob,text,prev,expected",
    [
        ("en", 0.95, "what is the weather tomorrow", "pt", "en"),
        ("pt", 0.95, "que tempo vai fazer amanhã", "en", "pt"),
        ("en", 0.95, "ok", "pt", "pt"),
        ("en", 0.95, "yes please", "pt", "pt"),
        ("en", 0.40, "what is the weather tomorrow", "pt", "pt"),
        ("es", 0.99, "qué tiempo hace mañana", "pt", "pt"),
        (None, 0.0, "", "en", "en"),
    ],
)
def test_choose_language(detected, prob, text, prev, expected):
    assert choose_language(detected, prob, text, prev) == expected
