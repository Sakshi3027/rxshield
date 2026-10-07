import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from graph.text2cypher import NotAnswerable
from ingestion.db import get_engine
from retrieval.rate_limit import RateLimited


@app.get("/_test/ok")
def ok_route():
    return {"ok": True}


@app.get("/_test/forbidden")
def forbidden_route():
    raise PermissionError("role cannot see inventory")


@app.get("/_test/limited")
def limited_route():
    raise RateLimited("user quota")


@app.get("/_test/unanswerable")
def unanswerable_route():
    raise NotAnswerable("no graph path")


@app.get("/_test/crash")
def crash_route():
    raise RuntimeError("password=hunter2-secret")


client = TestClient(app, raise_server_exceptions=False)


def test_health_is_untraced():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-trace-id" not in response.headers


def test_every_traced_response_carries_a_trace_id():
    response = client.get("/_test/ok")
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-trace-id"])


@pytest.mark.parametrize("path, status, code, internal", [
    ("/_test/forbidden", 403, "forbidden", "role cannot"),
    ("/_test/limited", 429, "rate_limited", "user quota"),
    ("/_test/unanswerable", 422, "not_answerable", "graph path"),
])
def test_known_errors_map_to_fixed_responses(path, status, code, internal):
    response = client.get(path)
    assert response.status_code == status
    assert response.json()["error"] == code
    assert internal not in response.text


def test_unexpected_error_hides_details_but_is_traced():
    response = client.get("/_test/crash")
    assert response.status_code == 500
    assert "hunter2" not in response.text
    with get_engine().connect() as conn:
        row = conn.execute(text(
            "select status, error_type from ops.spans where trace_id = :t and name = 'http'"),
            {"t": response.headers["x-trace-id"]}).one()
    assert (row.status, row.error_type) == ("error", "RuntimeError")


def test_ready_checks_both_databases():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"postgres": "ok", "neo4j": "ok"}}