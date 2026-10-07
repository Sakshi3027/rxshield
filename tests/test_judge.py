from evals.judge import parse_json, plant_number


def test_number_swap_skips_citations_and_avoids_source_numbers():
    answer = "Store at 2 °C to 8 °C [1]."
    swapped, decoy = plant_number(answer, "Store refrigerated at 2 °C to 8 °C.")
    assert swapped == f"Store at {decoy} °C to 8 °C [1]."
    assert decoy not in "Store refrigerated at 2 °C to 8 °C."


def test_answer_with_only_citations_has_nothing_to_swap():
    assert plant_number("See [1] and [L2].", "source") == (None, None)


def test_parse_json_strips_code_fences():
    assert parse_json('```json\n{"claims": []}\n```') == {"claims": []}