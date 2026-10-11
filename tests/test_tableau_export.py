"""The Tableau export publishes to the open internet, so it must read only public analytics marts."""
import re

import pandas as pd

from tableau.export import QUERIES, explode_countries


def test_export_reads_only_public_marts():
    for name, sql in QUERIES.items():
        tables = re.findall(r"\b(?:from|join)\s+([\w.]+)", sql, flags=re.IGNORECASE)
        assert tables, name
        assert all(table.startswith("analytics.mart_") for table in tables), (name, tables)


def test_explode_countries_flags_single_country_drugs():
    risk = pd.DataFrame({
        "drug_rxcui": ["1", "2", "3"],
        "drug_name": ["A", "B", "C"],
        "risk_tier": ["critical", "high", "elevated"],
        "manufacturing_countries": ["India, China", "India", None],
    })
    rows = explode_countries(risk)
    assert sorted(rows[rows.drug_rxcui == "1"].country) == ["China", "India"]
    assert rows.set_index("drug_rxcui").loc["2", "single_country"]
    assert not rows[rows.drug_rxcui == "1"].single_country.any()
    assert "3" not in set(rows.drug_rxcui)
