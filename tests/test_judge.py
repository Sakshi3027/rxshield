from evals.judge import (appears, build_variants, contains_marker, parse_json, plant_number,
                         shift_number, unverified_numbers, valid_verdict)


def test_number_swap_skips_citations_and_avoids_source_numbers():
    answer = "Store at 2 °C to 8 °C [1]."
    swapped, decoy = plant_number(answer, "Store refrigerated at 2 °C to 8 °C.")
    assert swapped == f"Store at {decoy} °C to 8 °C [1]."
    assert not appears(decoy, "Store refrigerated at 2 °C to 8 °C.")


def test_answer_with_only_citations_has_nothing_to_swap():
    assert plant_number("See [1] and [L2].", "source") == (None, None)


def test_number_shift_is_small_and_absent_from_source():
    shifted, decoy = shift_number("Discard after 8 hours [1].", "Discard after 8 hours. Store at 9 °C.")
    assert decoy == "7"
    assert shifted == "Discard after 7 hours [1]."


def test_appears_matches_whole_numbers_only():
    assert appears("9", "store at 9 °C")
    assert not appears("9", "approved in 1999")
    assert not appears("5", "use 0.5 mg")


def test_marker_requires_the_planted_value():
    assert contains_marker("9", "Discard after 9 hours.")
    assert not contains_marker("9", "Approved in 2019.")
    assert contains_marker("India", "Manufactured in India.")


def test_plausible_claim_uses_a_country_absent_from_source():
    variants = dict((kind, marker) for kind, _, marker in build_variants("Made in India [G].", "Plant in India."))
    assert variants["plausible_claim"] == "China"


def test_parse_json_strips_code_fences():
    assert parse_json('```json\n{"claims": []}\n```') == {"claims": []}

def test_verdict_shape_is_enforced():
    assert valid_verdict({"claims": [{"claim": "Store cold.", "supported": True}]})
    assert valid_verdict({"claims": []})
    assert not valid_verdict({"claims": ["Store cold."]})
    assert not valid_verdict({"claims": [{"claim": "Store cold.", "supported": "yes"}]})
    assert not valid_verdict(["Store cold."])


def test_unverified_numbers_lists_only_numbers_missing_from_source():
    answer = "3 drugs are affected [G]; store at 2 °C to 9 °C [1]."
    assert unverified_numbers(answer, "Store at 2 °C to 8 °C. Rows: a, b, c") == ["3", "9"]