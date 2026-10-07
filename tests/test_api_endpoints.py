import os

from fastapi.testclient import TestClient

import api.main as main
from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def auth(user_id):
    response = client.post("/auth/login", json={"user_id": user_id, "password": os.environ["DEMO_PASSWORD"]})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def fake_answer(calls):
    def answer(user_id, question):
        calls.append(user_id)
        return {"answer": "Stock covers 12 days [H].", "cache": "miss", "trace_id": "t"}
    return answer


def test_ask_requires_a_token():
    assert client.post("/ask", json={"question": "How many days of morphine do we have?"}).status_code == 401


def test_ask_uses_the_token_identity(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "cached_answer_for_user", fake_answer(calls))
    response = client.post("/ask", json={"question": "How many days of morphine do we have?"},
                           headers=auth("northshore-pharmacist"))
    assert response.status_code == 200
    assert calls == ["northshore-pharmacist"]
    assert response.json()["sources"]["labels"] == []


def test_ask_rejects_a_smuggled_user_id(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "cached_answer_for_user", fake_answer(calls))
    response = client.post("/ask", json={"question": "How many days of morphine do we have?",
                                         "user_id": "sunbelt-executive"},
                           headers=auth("northshore-pharmacist"))
    assert response.status_code == 422
    assert calls == []


def test_whatif_gives_pharmacist_patient_impact():
    response = client.post("/simulations/whatif", json={"scope": "country", "entity": "ind", "duration_days": 60},
                           headers=auth("northshore-pharmacist"))
    body = response.json()
    assert response.status_code == 200
    assert body["entity"] == "IND"
    assert isinstance(body["patients_affected"], int)
    assert all("patients_at_risk" in drug for drug in body["drugs"])


def test_whatif_hides_patients_from_procurement():
    response = client.post("/simulations/whatif", json={"scope": "country", "entity": "IND", "duration_days": 60},
                           headers=auth("northshore-procurement"))
    body = response.json()
    assert response.status_code == 200
    assert body["patients_affected"] is None
    assert not any("patients" in drug for drug in body["drugs"])


def test_whatif_is_forbidden_for_clinicians():
    response = client.post("/simulations/whatif", json={"scope": "country", "entity": "IND", "duration_days": 60},
                           headers=auth("northshore-clinician"))
    assert response.status_code == 403


def test_whatif_rejects_invalid_input():
    response = client.post("/simulations/whatif", json={"scope": "planet", "entity": "IND'; drop", "duration_days": 0},
                           headers=auth("northshore-pharmacist"))
    assert response.status_code == 422