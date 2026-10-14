from evals.benchmark import contains, score


def question(**fields):
    return {"expected": [], "forbidden": [], **fields}


def test_numbers_match_whole_values_only():
    assert contains("12", "we have 12 units")
    assert not contains("12", "we have 112 units")
    assert not contains("12", "back in 2012")


def test_text_terms_still_match_as_prefixes():
    assert contains("refrigerat", "store refrigerated at 2 to 8 c")


def test_thousands_separators_do_not_break_a_match():
    result = score("We have 3,232 units on hand.", question(expected=["3232"]))
    assert result["passed"]


def test_denial_passes_when_nothing_leaks():
    result = score("You don't have access to inventory.", question(deny=True, forbidden=["554"]))
    assert result["passed"]


def test_denial_fails_when_a_secret_leaks():
    result = score("There are 554 units on hand.", question(deny=True, forbidden=["554"]))
    assert not result["passed"]
    assert result["forbidden_found"] == ["554"]