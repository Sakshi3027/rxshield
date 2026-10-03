"""Prove tenant isolation and audit log protections hold at the database level."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tenancy.db import get_app_engine, tenant_session


def test_tenant_sees_only_its_own_users():
    with tenant_session("northshore") as conn:
        tenants = conn.execute(text("select distinct tenant_id from tenancy.users")).scalars().all()
    assert tenants == ["northshore"]


def test_no_tenant_context_sees_nothing():
    with get_app_engine().connect() as conn:
        count = conn.execute(text("select count(*) from tenancy.users")).scalar()
    assert count == 0


def test_cannot_write_audit_entries_for_another_tenant():
    with pytest.raises(DBAPIError):
        with tenant_session("northshore") as conn:
            conn.execute(text(
                "insert into tenancy.audit_log (tenant_id, user_id, role, action) "
                "values ('sunbelt', 'northshore-pharmacist', 'pharmacist', 'test')"))


def test_audit_log_cannot_be_deleted():
    with pytest.raises(DBAPIError):
        with tenant_session("northshore") as conn:
            conn.execute(text("delete from tenancy.audit_log"))