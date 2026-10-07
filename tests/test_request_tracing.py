from types import SimpleNamespace

import pandas as pd
from sqlalchemy import text

from ingestion.db import get_engine
from observability.tracing import span
from retrieval import llm
from retrieval.router import answer_routed


def fake_client(content):
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
    )
    completions = SimpleNamespace(create=lambda **kwargs: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_label_route_is_one_traced_request(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake_client("Store vials refrigerated."))
    with span("test_case") as case:
        result = answer_routed("How should Nipent vials be stored?")
    with get_engine().connect() as conn:
        spans = pd.read_sql(text("select * from ops.spans where trace_id = :t"),
                            conn, params={"t": case.trace_id})
    assert result["trace_id"] == case.trace_id
    by_name = spans.set_index("name")
    request = by_name.loc["request"]
    assert request["parent_id"] == case.span_id
    assert request["attributes"]["route"] == "label"
    for step in ("route", "label_lookup", "label_search", "llm"):
        assert by_name.loc[step, "parent_id"] == request["span_id"]
    assert by_name.loc["label_lookup", "attributes"]["labels"] > 0
    assert "nipent vials" not in str(spans["attributes"].tolist()).lower()