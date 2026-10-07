from agent.shortage_memo import RUNWAY_MARKER, check_draft, insert_runway, runway_table

INVENTORY = [
    {"drug_rxcui": "101", "drug_name": "Drug B 10 MG/ML", "on_hand_units": 400, "days_on_hand": 30},
    {"drug_rxcui": "102", "drug_name": "Drug A 20 MG/ML", "on_hand_units": 120, "days_on_hand": 6},
    {"drug_rxcui": "103", "drug_name": "Drug C 5 MG/ML", "on_hand_units": 50, "days_on_hand": None},
]
EVIDENCE = {"risk": [], "inventory": INVENTORY, "documents": [], "urgent_days": 14}


def memo(runway):
    return ("## Situation\nTwo products are at risk [R].\n\n"
            f"## Supply runway\n{runway}\nOne product is urgent [H].\n\n"
            "## Protocol\nNot available in evidence.\n\n"
            "## Alternatives\nNot available in evidence.\n\n"
            "## Recommended actions\n1. Reorder the urgent product [H].")


def test_runway_table_sorts_by_days_on_hand():
    rows = runway_table(INVENTORY).splitlines()[2:]
    assert [row.split("|")[1].strip() for row in rows] == ["Drug A 20 MG/ML", "Drug B 10 MG/ML", "Drug C 5 MG/ML"]


def test_inserted_table_passes_validation():
    draft = insert_runway(memo(RUNWAY_MARKER), runway_table(INVENTORY))
    assert RUNWAY_MARKER not in draft
    assert check_draft(draft, EVIDENCE) == []


def test_model_written_table_is_rejected():
    handmade = ("| Product | On hand (units) | Days on hand |\n|---|---:|---:|\n"
                "| Drug B 10 MG/ML | 400 | 30 |\n| Drug A 20 MG/ML | 120 | 6 |")
    assert any("Supply runway" in p for p in check_draft(memo(handmade), EVIDENCE))


def test_extra_rows_next_to_generated_table_are_rejected():
    runway = insert_runway(RUNWAY_MARKER, runway_table(INVENTORY)) + "| Drug A 20 MG/ML | 120 | 6 |"
    assert any("Supply runway" in p for p in check_draft(memo(runway), EVIDENCE))
