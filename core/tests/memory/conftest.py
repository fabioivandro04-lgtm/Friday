import pytest

from friday.memory.store import MemoryStore

# Cada eixo representa um tema; textos sem tema caem no último eixo.
_AXES = [("reuni", "manhã"), ("café",), ("bacalhau", "receita")]


class FakeEmbedder:
    dim = 4

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            low = text.lower()
            vec = [1.0 if any(k in low for k in keys) else 0.0 for keys in _AXES]
            vec.append(0.0 if any(vec) else 1.0)
            out.append(vec)
        return out


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def store(tmp_path, fake_embedder):
    return MemoryStore(str(tmp_path / "m.db"), fake_embedder, min_similarity=0.35)
