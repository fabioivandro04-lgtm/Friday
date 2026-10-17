from friday.memory.tools import make_memory_tools


async def test_remember_and_recall(store):
    remember, recall = make_memory_tools(store)
    assert remember.mutating is False and recall.mutating is False
    assert await remember.handler(fact="Gosto de café") == "Guardado."
    assert await remember.handler(fact="Gosto de café!") == "Já sabia."
    assert "Gosto de café" in await recall.handler(query="café")


async def test_recall_nothing(store):
    _, recall = make_memory_tools(store)
    assert await recall.handler(query="bacalhau") == "Não tenho nada guardado sobre isso."
