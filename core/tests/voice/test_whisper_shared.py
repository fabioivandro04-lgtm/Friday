import threading

from friday.voice.whisper_model import SharedWhisper


def test_loads_once_across_threads():
    loads = []

    def loader(name, device):
        loads.append(1)
        return object()

    shared = SharedWhisper("large-v3-turbo", "cuda", loader=loader)
    got = []
    threads = [threading.Thread(target=lambda: got.append(shared.get())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(loads) == 1 and len({id(m) for m in got}) == 1
