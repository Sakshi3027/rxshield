"""Prove role-aware evidence assembly without any LLM calls."""
import pytest
from sqlalchemy import text

from ingestion.db import get_engine
from retrieval.tenant_rag import gather_tenant_evidence

QUESTION = "What is our supply, our protocol, and our contract price?"


def northshore_rxcuis():
    with get_engine().connect() as conn:
        return conn.execute(text(
            "select drug_rxcui from tenancy.formulary where tenant_id = 'northshore' limit 5")).scalars().all()


def test_clinician_gets_no_inventory_and_only_protocols():
    evidence = gather_tenant_evidence("northshore-clinician", QUESTION, northshore_rxcuis())
    assert evidence["inventory"] == []
    assert {d["doc_type"] for d in evidence["private_sources"]} == {"protocol"}


def test_pharmacist_gets_inventory_without_prices():
    evidence = gather_tenant_evidence("northshore-pharmacist", QUESTION, northshore_rxcuis())
    assert evidence["inventory"]
    assert all(row["unit_price"] is None for row in evidence["inventory"])


def test_procurement_gets_inventory_with_prices():
    evidence = gather_tenant_evidence("northshore-procurement", QUESTION, northshore_rxcuis())
    assert evidence["inventory"]
    assert all(row["unit_price"] is not None for row in evidence["inventory"])


def test_unknown_user_is_rejected():
    with pytest.raises(PermissionError):
        gather_tenant_evidence("intruder", QUESTION, northshore_rxcuis())