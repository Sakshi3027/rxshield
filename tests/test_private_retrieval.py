"""Prove private retrieval respects tenant and role permissions, and that every search is audited."""
from sqlalchemy import text

from retrieval.private_search import search_private
from tenancy.db import user_session


def test_clinician_gets_only_own_clinical_protocols():
    results = search_private("northshore-clinician", "substitution protocol and contract price", k=10)
    assert results
    assert {r["tenant_id"] for r in results} == {"northshore"}
    assert {r["doc_type"] for r in results} == {"protocol"}


def test_procurement_gets_only_own_procurement_memos():
    results = search_private("northshore-procurement", "contract price and wholesaler allocation", k=10)
    assert results
    assert {r["tenant_id"] for r in results} == {"northshore"}
    assert {r["doc_type"] for r in results} == {"procurement_memo"}


def test_naming_another_hospital_cannot_reach_its_documents():
    results = search_private("northshore-executive", "Sunbelt Community Hospitals procurement memo", k=20)
    assert results
    assert all(r["tenant_id"] == "northshore" for r in results)


def test_every_search_is_audited():
    def audit_count():
        with user_session("northshore-executive") as conn:
            return conn.execute(text(
                "select count(*) from tenancy.audit_log "
                "where user_id = 'northshore-clinician' and action = 'private_search'")).scalar()

    before = audit_count()
    search_private("northshore-clinician", "heparin protocol")
    assert audit_count() == before + 1