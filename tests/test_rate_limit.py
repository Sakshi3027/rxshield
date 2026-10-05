"""Prove a user is rate limited after reaching the quota, using a disposable test user."""
import pytest
from sqlalchemy import text

from ingestion.db import get_engine
from retrieval.rate_limit import USER_LIMIT_PER_MINUTE, quota_exceeded
from tenancy.audit import log_access
from tenancy.db import user_session

TEST_USER = "greatlakes-ratetest"


@pytest.fixture
def test_user():
    with get_engine().begin() as conn:
        conn.execute(text(
            "insert into tenancy.users (user_id, tenant_id, display_name, role) "
            "values (:u, 'greatlakes', 'Rate Test', 'pharmacist') on conflict (user_id) do nothing"),
            {"u": TEST_USER})
    yield TEST_USER
    with get_engine().begin() as conn:
        conn.execute(text("delete from tenancy.audit_log where user_id = :u"), {"u": TEST_USER})
        conn.execute(text("delete from tenancy.users where user_id = :u"), {"u": TEST_USER})


def test_user_is_limited_after_reaching_quota(test_user):
    with user_session(test_user) as conn:
        assert quota_exceeded(conn) is None
        for _ in range(USER_LIMIT_PER_MINUTE):
            log_access(conn, "answer", "TEST rate limit request")
        assert quota_exceeded(conn) is not None