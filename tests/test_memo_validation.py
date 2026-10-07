"""The memo validator must catch missing sections and invented numbers without any LLM call."""
from agent.shortage_memo import REQUIRED_SECTIONS, check_draft, normalize

EVIDENCE = normalize('{"inventory":[{"on_hand_units":406,"days_on_hand":7,"unit_price":"178.68"}]}')
GOOD = "\n".join(REQUIRED_SECTIONS) + "\nWe have 406 units [H], about 7 days, at $178.68 per unit [H]."


def test_grounded_draft_passes():
    assert check_draft(GOOD, EVIDENCE) == []


def test_invented_number_is_caught():
    problems = check_draft(GOOD + " Supply lasts 14 days.", EVIDENCE)
    assert any("14" in p for p in problems)


def test_missing_section_is_caught():
    problems = check_draft(GOOD.replace("## Alternatives", ""), EVIDENCE)
    assert any("Alternatives" in p for p in problems)