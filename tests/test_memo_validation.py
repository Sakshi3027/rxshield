"""The memo validator must catch missing sections, invented numbers, omitted urgent items, and unused protocols."""
from agent.shortage_memo import check_draft

EVIDENCE = {
    "inventory": [
        {"drug_name": "Lidocaine A", "on_hand_units": 406, "days_on_hand": 7, "unit_price": "178.68"},
        {"drug_name": "Lidocaine B", "on_hand_units": 3010, "days_on_hand": 59, "unit_price": "40.10"},
    ],
    "documents": [{"id": "P1", "title": "Substitution protocol", "content": "Reserve stock for ICU."}],
}
GOOD = (
    "## Situation\nLidocaine is constrained [H].\n"
    "## Supply runway\nLidocaine A: 406 units, 7 days [H].\n"
    "## Protocol\nReserve stock for ICU [P1].\n"
    "## Alternatives\nOther labelers exist [R].\n"
    "## Recommended actions\nConserve Lidocaine A [H][P1]."
)


def test_grounded_complete_draft_passes():
    assert check_draft(GOOD, EVIDENCE) == []


def test_invented_number_is_caught():
    assert any("14" in p for p in check_draft(GOOD + " Lasts 14 days.", EVIDENCE))


def test_missing_section_is_caught():
    assert any("Alternatives" in p for p in check_draft(GOOD.replace("## Alternatives", ""), EVIDENCE))


def test_omitted_urgent_item_is_caught():
    draft = GOOD.replace("Lidocaine A: 406 units, 7 days [H].", "Supply looks fine [H].")
    assert any("urgent item missing" in p for p in check_draft(draft, EVIDENCE))


def test_unused_protocol_is_caught():
    draft = GOOD.replace("Reserve stock for ICU [P1].", "Not available in evidence.")
    assert any("Protocol section" in p for p in check_draft(draft, EVIDENCE))