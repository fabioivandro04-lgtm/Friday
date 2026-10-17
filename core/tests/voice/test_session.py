from friday.voice.session import SessionSlot


async def test_new_session_replaces_old():
    slot = SessionSlot()
    stopped = []

    async def stop_a():
        stopped.append("a")

    first = await slot.claim(stop_a)
    second = await slot.claim(lambda: None)
    assert stopped == ["a"]
    assert first != second


async def test_release_only_by_current_holder():
    slot = SessionSlot()
    stopped = []

    async def stop_a():
        stopped.append("a")

    old = await slot.claim(stop_a)
    await slot.claim(lambda: None)
    slot.release(old)  # a sessão antiga a terminar não liberta a nova

    async def stop_c():
        stopped.append("c")

    await slot.claim(stop_c)
    assert stopped == ["a"]  # a do meio (lambda) não é async e foi ignorada sem erro
