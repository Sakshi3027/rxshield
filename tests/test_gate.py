from evals.gate import decide


def row(**overrides):
    base = {"id": "q", "passed": True, "missing": [], "forbidden_found": [], "unverified_numbers": [],
            "faithfulness": 1.0, "unsupported": [], "judge_error": False}
    return {**base, **overrides}


def results(rows):
    return {name: ok for name, _, _, ok in decide(rows)}


def test_clean_run_passes_every_check():
    assert all(results([row(), row()]).values())


def test_one_ungrounded_number_fails_the_gate():
    assert not results([row(), row(unverified_numbers=["9"])])["Answers with ungrounded numbers"]


def test_one_benchmark_miss_in_ten_is_tolerated_but_two_are_not():
    assert results([row()] * 9 + [row(passed=False)])["Benchmark pass rate"]
    assert not results([row()] * 8 + [row(passed=False)] * 2)["Benchmark pass rate"]


def test_answers_without_claims_do_not_count_toward_faithfulness():
    assert results([row(faithfulness=None), row(faithfulness=1.0)])["Mean judged faithfulness"]


def test_unjudged_run_fails_closed():
    checks = results([row(faithfulness=None, judge_error=True)])
    assert not checks["Mean judged faithfulness"]
    assert not checks["Judge errors"]