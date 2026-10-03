"""Generate synthetic, reproducible formulary and contract data for each hospital tenant."""
import random
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from ingestion.db import get_engine

TENANT_SIZES = {"northshore": 220, "greatlakes": 180, "sunbelt": 150}
HIGH_RISK = {"critical", "high"}


def main():
    engine = get_engine()
    drugs = pd.read_sql("""
        select r.drug_rxcui, r.drug_name, r.risk_tier,
               (select min(se.company_name)
                from analytics.stg_package_drugs pd
                join analytics.stg_shortage_events se on se.package_ndc = pd.package_ndc
                where pd.drug_rxcui = r.drug_rxcui) as supplier
        from analytics.mart_shortage_risk r""", engine)

    formulary, contracts = [], []
    for tenant_id, size in TENANT_SIZES.items():
        rng = random.Random(tenant_id)
        picked = drugs.sample(n=size, random_state=rng.randint(0, 10**6))
        for d in picked.itertuples():
            daily = round(rng.uniform(2, 60), 1)
            days = rng.uniform(1, 10) if d.risk_tier in HIGH_RISK else rng.uniform(5, 60)
            formulary.append({"tenant_id": tenant_id, "drug_rxcui": d.drug_rxcui, "drug_name": d.drug_name,
                              "on_hand_units": int(daily * days), "avg_daily_units": daily})
            contracts.append({"tenant_id": tenant_id, "drug_rxcui": d.drug_rxcui,
                              "supplier": d.supplier or "Unlisted supplier",
                              "unit_price": round(rng.uniform(2, 400), 2),
                              "contract_end": date.today() + timedelta(days=rng.randint(30, 720))})

    with engine.begin() as conn:
        conn.execute(text("delete from tenancy.contracts"))
        conn.execute(text("delete from tenancy.formulary"))
        conn.execute(text(
            "insert into tenancy.formulary (tenant_id, drug_rxcui, drug_name, on_hand_units, avg_daily_units) "
            "values (:tenant_id, :drug_rxcui, :drug_name, :on_hand_units, :avg_daily_units)"), formulary)
        conn.execute(text(
            "insert into tenancy.contracts (tenant_id, drug_rxcui, supplier, unit_price, contract_end) "
            "values (:tenant_id, :drug_rxcui, :supplier, :unit_price, :contract_end)"), contracts)
    print(f"Seeded {len(formulary)} formulary rows and {len(contracts)} contracts across {len(TENANT_SIZES)} tenants")


if __name__ == "__main__":
    main()