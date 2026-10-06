"""What-if simulation: if a facility, company, or country goes offline, which of a hospital's drugs run out, and when?"""
import sys

import numpy as np
import pandas as pd
from sqlalchemy import text

from tenancy.audit import log_access
from tenancy.db import user_session

USAGE_VARIABILITY = 0.2
SIMULATIONS = 2000
SCOPES = {"facility": "duns", "company": "company_duns", "country": "country_code"}
SITE_COLUMNS = ["drug_rxcui", "duns", "company_duns", "country_code"]

INVENTORY_SQL = "select drug_rxcui, drug_name, on_hand_units, avg_daily_units from tenancy.formulary"
SITES_SQL = """
    with drug_products as (
        select distinct pd.drug_rxcui, se.product_ndc
        from analytics.stg_package_drugs pd
        join analytics.stg_shortage_events se on se.package_ndc = pd.package_ndc
        where pd.drug_rxcui = any(:rxcuis)
    )
    select distinct dp.drug_rxcui, o.duns, coalesce(f.registrant_duns, f.duns) as company_duns, f.country_code
    from drug_products dp
    join analytics.stg_establishment_operations o
        on o.product_ndc = dp.product_ndc and o.operation = 'MANUFACTURE'
    join analytics.stg_facilities f on f.duns = o.duns
"""
ALTERNATIVES_SQL = """
    select drug_rxcui, alternative_labeler_count
    from analytics.mart_drug_supply where drug_rxcui = any(:rxcuis)
"""


def classify(drug_sites, scope, entity):
    if drug_sites.empty:
        return "unknown", 0.0
    disrupted = int((drug_sites[SCOPES[scope]] == entity).sum())
    if disrupted == 0:
        return "unaffected", 0.0
    if disrupted == len(drug_sites):
        return "lost", 1.0
    return "partial", disrupted / len(drug_sites)


def simulate(inventory, sites, scope, entity, duration_days, simulations=SIMULATIONS, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for drug in inventory.itertuples():
        drug_sites = sites[sites["drug_rxcui"] == drug.drug_rxcui].drop_duplicates("duns")
        status, lost_fraction = classify(drug_sites, scope, entity)
        row = {"drug_rxcui": drug.drug_rxcui, "drug_name": drug.drug_name, "status": status,
               "sites": len(drug_sites), "p_stockout": 0.0, "median_days_to_runout": None,
               "expected_stockout_days": 0.0}
        if lost_fraction > 0:
            average = float(drug.avg_daily_units)
            usage = np.clip(rng.normal(average, USAGE_VARIABILITY * average, simulations), 0.01, None)
            days_to_runout = float(drug.on_hand_units) / (usage * lost_fraction)
            row.update({
                "p_stockout": round(float((days_to_runout < duration_days).mean()), 3),
                "median_days_to_runout": round(float(np.median(days_to_runout)), 1),
                "expected_stockout_days": round(float(np.clip(duration_days - days_to_runout, 0, None).mean()), 1),
            })
        rows.append(row)
    return pd.DataFrame(rows)


def run_whatif(user_id, scope, entity, duration_days):
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {sorted(SCOPES)}")
    description = f"{scope} {entity} offline for {duration_days} days"

    with user_session(user_id) as conn:
        inventory = pd.DataFrame(conn.execute(text(INVENTORY_SQL)).mappings().all())
        if inventory.empty:
            log_access(conn, "simulation", description, {}, outcome="no_inventory_access")
        else:
            rxcuis = inventory["drug_rxcui"].tolist()
            sites = pd.DataFrame(
                conn.execute(text(SITES_SQL), {"rxcuis": rxcuis}).mappings().all(), columns=SITE_COLUMNS)
            alternatives = pd.DataFrame(
                conn.execute(text(ALTERNATIVES_SQL), {"rxcuis": rxcuis}).mappings().all(),
                columns=["drug_rxcui", "alternative_labeler_count"])
            result = simulate(inventory, sites, scope, entity, duration_days)
            result = result.merge(alternatives, on="drug_rxcui", how="left")
            affected = result[result["status"].isin(["lost", "partial"])]
            log_access(conn, "simulation", description, {
                "drugs_affected": len(affected),
                "likely_stockouts": int((affected["p_stockout"] >= 0.5).sum())})
    if inventory.empty:
        raise PermissionError("Inventory is not available to this user, so the simulation cannot run.")
    return result


def main():
    user_id, scope, entity, duration = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    try:
        result = run_whatif(user_id, scope, entity, duration)
    except PermissionError as err:
        print(err)
        return

    print(f"Scenario: {scope} {entity} offline for {duration} days\n")
    print(result["status"].value_counts().to_string(), "\n")
    at_risk = result[result["status"].isin(["lost", "partial"])].sort_values(
        ["p_stockout", "median_days_to_runout"], ascending=[False, True])
    for row in at_risk.itertuples():
        alternatives = int(row.alternative_labeler_count) if pd.notna(row.alternative_labeler_count) else 0
        print(f"{row.drug_name[:48]:<48} {row.status:<8} P(stockout)={row.p_stockout:<5} "
              f"runout~day {row.median_days_to_runout:<6} alt sources: {alternatives}")


if __name__ == "__main__":
    main()