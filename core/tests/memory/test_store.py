from friday.memory.store import MemoryStore


def test_add_and_search(store):
    store.add_fact("O Fábio prefere reuniões de manhã")
    assert store.search("quando gosto de reuniões?") == ["O Fábio prefere reuniões de manhã"]


def test_unrelated_query_returns_nothing(store):
    store.add_fact("O Fábio prefere reuniões de manhã")
    assert store.search("receita de bacalhau") == []


def test_near_duplicate_not_stored_twice(store):
    assert store.add_fact("O Fábio prefere reuniões de manhã") is True
    assert store.add_fact("O Fábio prefere reuniões de manhã.") is False


def test_empty_fact_rejected(store):
    assert store.add_fact("   ") is False


def test_persists_across_instances(tmp_path, fake_embedder):
    path = str(tmp_path / "m.db")
    MemoryStore(path, fake_embedder).add_fact("Gosto de café")
    assert MemoryStore(path, fake_embedder).search("café") == ["Gosto de café"]


def test_context_for_empty_is_blank(store):
    assert store.context_for("qualquer coisa") == ""


def test_context_for_joins_facts(store):
    store.add_fact("O Fábio prefere reuniões de manhã")
    assert store.context_for("reuniões") == "O Fábio prefere reuniões de manhã"


def test_log_turn_does_not_become_fact(store):
    store.log_turn("user", "Gosto de café")
    assert store.search("café") == []
