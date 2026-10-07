import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIConnectionError, RateLimitError

from api.main import app
from graph import db
from retrieval.cache import vocabulary
from retrieval.vector_search import get_model

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@app.get("/_test/llm-limit")
def llm_limit_route():
    request = httpx.Request("POST", GROQ_URL)
    raise RateLimitError("limit reached", response=httpx.Response(429, request=request), body=None)


@app.get("/_test/llm-offline")
def llm_offline_route():
    raise APIConnectionError(request=httpx.Request("POST", GROQ_URL))


def test_get_driver_reuses_one_driver():
    with db.get_driver() as first, db.get_driver() as second:
        assert first is second


def test_lifespan_warms_resources_then_closes_driver():
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert get_model.cache_info().currsize == 1
        assert vocabulary.cache_info().currsize == 1
        assert db.shared_driver.cache_info().currsize == 1
    assert db.shared_driver.cache_info().currsize == 0


@pytest.mark.parametrize("path", ["/_test/llm-limit", "/_test/llm-offline"])
def test_llm_outage_is_503_not_500(path):
    response = TestClient(app, raise_server_exceptions=False).get(path)
    assert response.status_code == 503
    assert response.json()["error"] == "llm_unavailable"