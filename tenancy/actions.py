"""Create agent drafts and review them; who may do what is enforced by the database."""
import json

from sqlalchemy import text

from tenancy.audit import log_access
from tenancy.db import user_session


def create_action(conn, action_type, subject, draft, evidence):
    action_id = conn.execute(text("""
        insert into tenancy.agent_actions (tenant_id, created_by, action_type, subject, draft, evidence)
        values (tenancy.session_tenant(), current_setting('app.user_id', true),
                :action_type, :subject, :draft, cast(:evidence as jsonb))
        returning action_id"""),
        {"action_type": action_type, "subject": subject, "draft": draft,
         "evidence": json.dumps(evidence, default=str)}).scalar()
    log_access(conn, "action_draft", subject, {"action_id": action_id, "action_type": action_type})
    return action_id


def review_action(user_id, action_id, decision, note=None):
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    with user_session(user_id) as conn:
        reviewed = conn.execute(text("""
            update tenancy.agent_actions
            set status = :decision, reviewed_by = current_setting('app.user_id', true),
                review_note = :note, reviewed_at = now()
            where action_id = :action_id
            returning action_id"""),
            {"decision": decision, "note": note, "action_id": action_id}).scalar()
        if reviewed is None:
            raise PermissionError("Action not found, already reviewed, or you are not allowed to review it.")
        log_access(conn, "action_review", f"{decision} action {action_id}", {"action_id": action_id, "note": note})
    return reviewed


def pending_actions(user_id):
    with user_session(user_id) as conn:
        rows = conn.execute(text("""
            select action_id, action_type, subject, created_by, created_at
            from tenancy.agent_actions where status = 'pending_approval'
            order by created_at""")).mappings().all()
    return [dict(row) for row in rows]

def get_action(conn, action_id):
    row = conn.execute(text("""
        select action_id, subject, draft, status, review_note
        from tenancy.agent_actions where action_id = :action_id"""),
        {"action_id": action_id}).mappings().one_or_none()
    return dict(row) if row else None