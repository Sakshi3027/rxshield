"""Per-user and per-tenant answer quotas, counted from the audit log."""
from sqlalchemy import text

USER_LIMIT_PER_MINUTE = 10
TENANT_LIMIT_PER_MINUTE = 30


class RateLimited(Exception):
    pass


def quota_exceeded(conn):
    counts = conn.execute(text("select * from tenancy.recent_answer_counts(60)")).mappings().one()
    if counts["user_requests"] >= USER_LIMIT_PER_MINUTE:
        return f"User limit of {USER_LIMIT_PER_MINUTE} answers per minute reached. Please try again shortly."
    if counts["tenant_requests"] >= TENANT_LIMIT_PER_MINUTE:
        return f"Hospital limit of {TENANT_LIMIT_PER_MINUTE} answers per minute reached. Please try again shortly."
    return None