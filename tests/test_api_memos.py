import os

from fastapi.testclient import TestClient
from sqlalchemy import text

import api.main as main
from api.main import app
from ingestion.db import get_engine

client = TestClient(app, raise_server_exceptions=False)


def auth(user_id):
    response = client.post("/auth/login", json={"user_id": user_id, "password": os.environ["DEMO_PASSWORD"]})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def northshore_action_id():
    with get_engine().connect() as conn:
        return conn.execute(text(
            "select min(action_id) from tenancy.agent_actions where tenant_id = 'northshore'")).scalar()


def fake_memo(calls, saved=True):
    def draft(user_id, ingredient, revision_of=None):
        calls.append((user_id, ingredient, revision_of))
        return {"draft": "UNVALIDATED DRAFT TEXT", "attempts": 2, "tokens": 0,
                "problems": [] if saved else ["Number 47 is not in the evidence"],
                "action_id": 501 if saved else None}
    return draft


def test_memo_is_drafted_for_the_token_user(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "draft_memo", fake_memo(calls))
    response = client.post("/memos", json={"ingredient": "rocuronium"}, headers=auth("northshore-pharmacist"))
    assert response.status_code == 201
    assert response.json()["action_id"] == 501
    assert calls == [("northshore-pharmacist", "rocuronium", None)]


def test_failed_draft_returns_problems_but_never_the_draft(monkeypatch):
    monkeypatch.setattr(main, "draft_memo", fake_memo([], saved=False))
    response = client.post("/memos", json={"ingredient": "rocuronium"}, headers=auth("northshore-pharmacist"))
    assert response.status_code == 422
    assert response.json()["problems"] == ["Number 47 is not in the evidence"]
    assert "UNVALIDATED" not in response.text


def test_memo_rejects_injection_style_ingredient():
    response = client.post("/memos", json={"ingredient": "x'; drop table"}, headers=auth("northshore-pharmacist"))
    assert response.status_code == 422


def test_own_hospital_can_read_a_memo():
    response = client.get(f"/memos/{northshore_action_id()}", headers=auth("northshore-executive"))
    assert response.status_code == 200
    assert response.json()["draft"]


def test_other_hospital_gets_not_found_not_forbidden():
    response = client.get(f"/memos/{northshore_action_id()}", headers=auth("sunbelt-executive"))
    assert response.status_code == 404


def test_other_hospital_cannot_review():
    response = client.post(f"/memos/{northshore_action_id()}/review", json={"decision": "approved"},
                           headers=auth("sunbelt-executive"))
    assert response.status_code == 403


def test_pending_route_is_not_mistaken_for_a_memo_id():
    response = client.get("/memos/pending", headers=auth("northshore-executive"))
    assert response.status_code == 200
    assert isinstance(response.json()["memos"], list)


def test_review_decision_must_be_approve_or_reject():
    response = client.post(f"/memos/{northshore_action_id()}/review", json={"decision": "maybe"},
                           headers=auth("northshore-executive"))
    assert response.status_code == 422