from scripts.bench_latency import exit_code, summarise


def test_summarise_median_and_p90():
    assert summarise([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]) == {
        "median": 550,
        "p90": 910,
        "n": 10,
    }


def test_summarise_empty():
    assert summarise([]) == {"median": None, "p90": None, "n": 0}


def test_exit_code_against_target():
    assert exit_code({"median": 1300, "p90": 2000, "n": 5}) == 0
    assert exit_code({"median": 1301, "p90": 1400, "n": 5}) == 1
    assert exit_code({"median": None, "p90": None, "n": 0}) == 1
