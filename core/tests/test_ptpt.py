import pytest

from friday.ptpt import find_brazilianisms


@pytest.mark.parametrize(
    "text,found",
    [
        ("Você está no ônibus?", ["você", "ônibus"]),
        ("Estou fazendo isso no celular", ["estou fazendo", "celular"]),
        ("Estás no autocarro? Liga-me do telemóvel.", []),
        ("Tomei café da manhã e fui ao banheiro", ["café da manhã", "banheiro"]),
        ("Estou a fazer o jantar", []),
    ],
)
def test_find_brazilianisms(text, found):
    assert find_brazilianisms(text) == found
