"""Write audit entries using identity the database derives, never identity the caller claims."""
import json

from sqlalchemy import text


def log_access(conn, action, question=None, resources=None, outcome="ok"):
    conn.execute(text("""
        insert into tenancy.audit_log (tenant_id, user_id, role, action, question, resources, outcome)
        values (tenancy.session_tenant(), current_setting('app.user_id', true), tenancy.session_role(),
                :action, :question, cast(:resources as jsonb), :outcome)"""),
        {"action": action, "question": question,
         "resources": json.dumps(resources or []), "outcome": outcome})