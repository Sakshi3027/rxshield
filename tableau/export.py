"""Export public-only RxShield marts to CSV for the Tableau Public dashboard.

Tableau Public publishes its data to the open internet, so this script reads only the analytics
marts built from public FDA, RxNorm, and openFDA sources. It never reads tenancy tables
(inventory, contracts, protocols, patients); a test enforces that every query stays on analytics marts.
"""
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from ingestion.db import get_engine

OUT = Path(__file__).resolve().parent / "data"

QUERIES = {
    "shortage_risk": """
        select drug_rxcui, drug_name, risk_tier, has_current_shortage, alternative_status,
               alternative_labeler_count, manufacturing_site_count, manufacturing_countries,
               recalls_5y, class_1_recalls_5y, risk_reasons
        from analytics.mart_shortage_risk
        where not is_pack
    """,
    "company_exposure": """
        select company_name, facility_count, countries, shortage_products_manufactured, sole_company_products
        from analytics.mart_company_exposure
    """,
}


def explode_countries(risk: pd.DataFrame) -> pd.DataFrame:
    """One row per drug and manufacturing country, with how many countries make that drug."""
    rows = risk.dropna(subset=["manufacturing_countries"])[["drug_rxcui", "drug_name", "risk_tier", "manufacturing_countries"]]
    rows = rows.assign(country=rows["manufacturing_countries"].str.split(r"\s*[,;|]\s*")).explode("country")
    rows["country"] = rows["country"].str.strip()
    rows = rows[rows["country"].str.len() > 0].drop(columns="manufacturing_countries").drop_duplicates()
    rows["country_count"] = rows.groupby("drug_rxcui")["country"].transform("nunique")
    rows["single_country"] = rows["country_count"] == 1
    return rows.reset_index(drop=True)


def main():
    OUT.mkdir(exist_ok=True)
    with get_engine().connect() as conn:
        frames = {name: pd.read_sql(text(sql), conn) for name, sql in QUERIES.items()}
    frames["drug_countries"] = explode_countries(frames["shortage_risk"])
    for name, frame in frames.items():
        frame.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name:20} {len(frame):6} rows -> tableau/data/{name}.csv")


if __name__ == "__main__":
    main()
