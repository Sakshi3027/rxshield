"""Hand-checkable tests for the what-if simulation engine."""
import pandas as pd

from simulation.whatif import simulate

INVENTORY = pd.DataFrame([
    {"drug_rxcui": "a", "drug_name": "A", "on_hand_units": 100, "avg_daily_units": 10},
    {"drug_rxcui": "b", "drug_name": "B", "on_hand_units": 100, "avg_daily_units": 10},
    {"drug_rxcui": "c", "drug_name": "C", "on_hand_units": 600, "avg_daily_units": 10},
    {"drug_rxcui": "d", "drug_name": "D", "on_hand_units": 100, "avg_daily_units": 10},
])
SITES = pd.DataFrame([
    {"drug_rxcui": "a", "duns": "1", "company_duns": "x", "country_code": "IND"},
    {"drug_rxcui": "b", "duns": "2", "company_duns": "y", "country_code": "USA"},
    {"drug_rxcui": "c", "duns": "3", "company_duns": "x", "country_code": "IND"},
    {"drug_rxcui": "c", "duns": "4", "company_duns": "z", "country_code": "USA"},
])


def test_country_disruption_classifies_and_simulates_correctly():
    result = simulate(INVENTORY, SITES, "country", "IND", 60).set_index("drug_rxcui")
    assert result.loc["a", "status"] == "lost" and result.loc["a", "p_stockout"] == 1.0
    assert result.loc["b", "status"] == "unaffected" and result.loc["b", "p_stockout"] == 0.0
    assert result.loc["c", "status"] == "partial" and result.loc["c", "p_stockout"] < 0.01
    assert result.loc["d", "status"] == "unknown"


def test_company_disruption_uses_owner_not_country():
    result = simulate(INVENTORY, SITES, "company", "x", 60).set_index("drug_rxcui")
    assert result.loc["a", "status"] == "lost"
    assert result.loc["b", "status"] == "unaffected"
    assert result.loc["c", "status"] == "partial"