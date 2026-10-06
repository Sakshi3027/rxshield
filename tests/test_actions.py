"""Prove the approval workflow: separation of duties, role gates, immutability, and tenant isolation."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ingestion.db import get_engine
from tenancy.actions import create_action, review_action
from tenancy.db import user_session


@pytest.fixture
def pending_action():
    with user_session("northshore-pharmacist") as conn:
        action_id = create_action(conn, "test", "TEST action", "Draft text", {"source": "test"})
    yield action_id
    with get_engine().begin() as conn:
        conn.execute(text("delete from tenancy.agent_actions where subject = 'TEST action'"))


def test_creator_cannot_approve_own_draft(pending_action):
    with pytest.raises(DBAPIError, match="row-level security"):
        review_action("northshore-pharmacist", pending_action, "approved")


def test_clinician_cannot_review(pending_action):
    with pytest.raises(PermissionError):
        review_action("northshore-clinician", pending_action, "approved")


def test_other_hospital_cannot_review(pending_action):
    with pytest.raises(PermissionError):
        review_action("sunbelt-executive", pending_action, "approved")


def test_executive_can_approve_once(pending_action):
    assert review_action("northshore-executive", pending_action, "approved", "Looks right") == pending_action
    with pytest.raises(PermissionError):
        review_action("northshore-executive", pending_action, "rejected")


def test_draft_text_cannot_be_edited(pending_action):
    with pytest.raises(DBAPIError, match="permission denied"):
        with user_session("northshore-executive") as conn:
            conn.execute(text("update tenancy.agent_actions set draft = 'tampered' where action_id = :a"),
                         {"a": pending_action})