"""Patient impact of a what-if disruption, from FHIR MedicationRequest orders."""
import sys

import pandas as pd
from sqlalchemy import text

from simulation.whatif import run_whatif
from tenancy.audit import log_access
from tenancy.db import user_session

AT_RISK = ("lost", "partial")
ORDER_ROLES = ("pharmacist", "clinician", "executive")

ROLE_SQL = text("select tenancy.session_role()")
ORDERS_SQL = text("""
    select drug_rxcui, patient_ref, care_unit
    from tenancy.medication_orders
    where status = 'active' and drug_rxcui = any(:rxcuis)
""")
SUMMARY_COLUMNS = ["drug_rxcui", "active_orders", "patients", "icu_patients", "care_units"]


def summarize_orders(orders):
    """Per drug: active orders, distinct patients, distinct ICU patients, care units."""
    if orders.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    grouped = orders.groupby("drug_rxcui")
    icu = orders[orders["care_unit"] == "ICU"].groupby("drug_rxcui")["patient_ref"].nunique()
    summary = pd.DataFrame({
        "active_orders": grouped.size(),
        "patients": grouped["patient_ref"].nunique(),
        "icu_patients": icu,
        "care_units": grouped["care_unit"].agg(lambda s: ", ".join(sorted(s.unique()))),
    })
    summary["icu_patients"] = summary["icu_patients"].fillna(0).astype(int)
    return summary.reset_index()[SUMMARY_COLUMNS]


def run_patient_impact(user_id, scope, entity, duration_days):
    results = run_whatif(user_id, scope, entity, duration_days)
    at_risk = results[results["status"].isin(AT_RISK)].copy()
    description = f"{scope} {entity} {duration_days}d"

    with user_session(user_id) as conn:
        role = conn.execute(ROLE_SQL).scalar()
        if role not in ORDER_ROLES:
            log_access(conn, "patient_impact", description, {"outcome": "no_order_access"})
            return at_risk, None

        orders = pd.read_sql(ORDERS_SQL, conn, params={"rxcuis": at_risk["drug_rxcui"].tolist()})
        summary = summarize_orders(orders)
        total_patients = int(orders["patient_ref"].nunique())
        log_access(conn, "patient_impact", description, {
            "drugs_with_orders": len(summary),
            "patients_affected": total_patients,
        })

    impact = at_risk.merge(summary, on="drug_rxcui", how="left")
    for column in ["active_orders", "patients", "icu_patients"]:
        impact[column] = impact[column].fillna(0).astype(int)
    impact["care_units"] = impact["care_units"].fillna("")
    return impact, total_patients


if __name__ == "__main__":
    user_id, scope, entity, days = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    impact, total_patients = run_patient_impact(user_id, scope, entity, days)
    columns = ["drug_name", "status", "p_stockout", "patients", "icu_patients", "care_units"]
    if total_patients is None:
        columns = ["drug_name", "status", "p_stockout"]
        print("Patient impact is not available for your role.\n")
    else:
        print(f"Distinct patients on at-risk drugs: {total_patients}\n")
    ranked = impact.sort_values(["p_stockout"], ascending=False)
    print(ranked[columns].head(15).to_string(index=False))