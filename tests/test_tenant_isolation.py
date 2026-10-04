"""Prove tenant isolation, role permissions, and audit protections hold at the database level."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tenancy.db import get_app_engine, user_session


def count(conn, table):
    return conn.execute(text(f"select count(*) from {table}")).scalar()


def test_user_sees_only_their_own_tenant():
    with user_session("northshore-pharmacist") as conn:
        tenants = conn.execute(text("select distinct tenant_id from tenancy.users")).scalars().all()
    assert tenants == ["northshore"]


def test_no_user_context_sees_nothing():
    with get_app_engine().connect() as conn:
        assert count(conn, "tenancy.users") == 0
        assert count(conn, "tenancy.formulary") == 0


def test_unknown_user_sees_nothing():
    with user_session("intruder") as conn:
        assert count(conn, "tenancy.formulary") == 0
        assert count(conn, "tenancy.contracts") == 0


@pytest.mark.parametrize("user, sees_formulary, sees_contracts", [
    ("northshore-pharmacist", True, False),
    ("northshore-procurement", True, True),
    ("northshore-clinician", False, False),
    ("northshore-executive", True, True),
])
def test_role_based_visibility(user, sees_formulary, sees_contracts):
    with user_session(user) as conn:
        assert (count(conn, "tenancy.formulary") > 0) == sees_formulary
        assert (count(conn, "tenancy.contracts") > 0) == sees_contracts


def test_procurement_sees_only_own_contracts():
    with user_session("sunbelt-procurement") as conn:
        tenants = conn.execute(text("select distinct tenant_id from tenancy.contracts")).scalars().all()
    assert tenants == ["sunbelt"]


def test_cannot_forge_audit_entry_as_another_user():
    with pytest.raises(DBAPIError, match="row-level security"):
        with user_session("northshore-pharmacist") as conn:
            conn.execute(text(
                "insert into tenancy.audit_log (tenant_id, user_id, role, action) "
                "values ('northshore', 'northshore-executive', 'executive', 'test')"))

def test_audit_log_cannot_be_deleted():
    with pytest.raises(DBAPIError, match="permission denied"):
        with user_session("northshore-executive") as conn:
            conn.execute(text("delete from tenancy.audit_log"))

def test_onboarded_tenant_sees_only_its_own_data():
    with user_session("riverbend-pharmacist") as conn:
        formulary = conn.execute(text("select distinct tenant_id from tenancy.formulary")).scalars().all()
        users = conn.execute(text("select distinct tenant_id from tenancy.users")).scalars().all()
    assert formulary == ["riverbend"]
    assert users == ["riverbend"]