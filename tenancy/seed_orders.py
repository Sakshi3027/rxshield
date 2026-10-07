"""Generate synthetic active medication orders as validated FHIR R4B MedicationRequest resources."""
import random
from datetime import date, timedelta

import pandas as pd
from fhir.resources.R4B.medicationrequest import MedicationRequest
from sqlalchemy import text

from ingestion.db import get_engine

RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
CARE_UNITS = ["ICU", "Operating Room", "Emergency Department", "Med-Surg", "Oncology"]
PATIENTS_PER_TENANT = 300


def build_order(order_id, patient_ref, rxcui, drug_name, authored_on):
    resource = {
        "resourceType": "MedicationRequest",
        "id": order_id,
        "status": "active",
        "intent": "order",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/medicationrequest-category",
            "code": "inpatient", "display": "Inpatient"}]}],
        "medicationCodeableConcept": {
            "coding": [{"system": RXNORM, "code": rxcui, "display": drug_name}],
            "text": drug_name},
        "subject": {"reference": f"Patient/{patient_ref}"},
        "authoredOn": authored_on.isoformat(),
    }
    return MedicationRequest.model_validate(resource).model_dump_json(exclude_none=True)


def main():
    engine = get_engine()
    formulary = pd.read_sql(
        text("select tenant_id, drug_rxcui, drug_name, avg_daily_units from tenancy.formulary"), engine)

    orders = []
    for tenant_id, drugs in formulary.groupby("tenant_id"):
        rng = random.Random(f"orders-{tenant_id}")
        for drug in drugs.itertuples():
            for _ in range(rng.randint(0, max(1, int(float(drug.avg_daily_units) // 12)))):
                order_id = f"{tenant_id}-mr-{len(orders) + 1:05d}"
                patient_ref = f"{tenant_id}-pt-{rng.randint(1, PATIENTS_PER_TENANT):04d}"
                authored_on = date.today() - timedelta(days=rng.randint(0, 10))
                orders.append({
                    "order_id": order_id, "tenant_id": tenant_id, "patient_ref": patient_ref,
                    "drug_rxcui": drug.drug_rxcui, "care_unit": rng.choice(CARE_UNITS),
                    "status": "active", "authored_on": authored_on,
                    "resource": build_order(order_id, patient_ref, drug.drug_rxcui, drug.drug_name, authored_on),
                })

    with engine.begin() as conn:
        conn.execute(text("delete from tenancy.medication_orders"))
        conn.execute(text("""
            insert into tenancy.medication_orders
                (order_id, tenant_id, patient_ref, drug_rxcui, care_unit, status, authored_on, resource)
            values (:order_id, :tenant_id, :patient_ref, :drug_rxcui, :care_unit, :status, :authored_on,
                    cast(:resource as jsonb))"""), orders)

    summary = pd.DataFrame(orders).groupby("tenant_id").agg(
        orders=("order_id", "count"), patients=("patient_ref", "nunique"), drugs=("drug_rxcui", "nunique"))
    print(f"Seeded {len(orders)} validated FHIR MedicationRequest orders\n")
    print(summary.to_string())


if __name__ == "__main__":
    main()