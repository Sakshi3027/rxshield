"""Orders must be valid FHIR, and visible only to roles whose work requires them, within their own hospital."""
import json

from fhir.resources.R4B.medicationrequest import MedicationRequest
from sqlalchemy import text

from tenancy.db import user_session


def visible_tenants(user_id):
    with user_session(user_id) as conn:
        return conn.execute(text("select distinct tenant_id from tenancy.medication_orders")).scalars().all()


def test_pharmacist_and_clinician_see_only_own_orders():
    assert visible_tenants("northshore-pharmacist") == ["northshore"]
    assert visible_tenants("northshore-clinician") == ["northshore"]


def test_procurement_sees_no_patient_orders():
    assert visible_tenants("northshore-procurement") == []


def test_stored_orders_are_valid_fhir():
    with user_session("northshore-pharmacist") as conn:
        resources = conn.execute(text("select resource from tenancy.medication_orders limit 25")).scalars().all()
    assert resources
    for resource in resources:
        parsed = MedicationRequest.model_validate(resource if isinstance(resource, dict) else json.loads(resource))
        assert parsed.medicationCodeableConcept.coding[0].system == "http://www.nlm.nih.gov/research/umls/rxnorm"