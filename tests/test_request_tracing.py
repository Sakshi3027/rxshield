from types import SimpleNamespace

import pandas as pd
from sqlalchemy import text

from graph.text2cypher import NotAnswerable
from ingestion.db import get_engine
from observability.tracing import span
from retrieval import llm, tenant_rag
from retrieval.router import answer_routed


def fake_client(content):
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
    )
    completions = SimpleNamespace(create=lambda **kwargs: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def trace_spans(trace_id):
    with get_engine().connect() as conn:
        return pd.read_sql(text("select * from ops.spans where trace_id = :t"),
                           conn, params={"t": trace_id})


def test_label_route_is_one_traced_request(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake_client("Store vials refrigerated."))
    with span("test_case") as case:
        result = answer_routed("How should Nipent vials be stored?")
    spans = trace_spans(case.trace_id)
    assert result["trace_id"] == case.trace_id
    by_name = spans.set_index("name")
    request = by_name.loc["request"]
    assert request["parent_id"] == case.span_id
    assert request["attributes"]["route"] == "label"
    for step in ("route", "label_lookup", "label_search", "llm"):
        assert by_name.loc[step, "parent_id"] == request["span_id"]
    assert by_name.loc["label_lookup", "attributes"]["labels"] > 0
    assert "nipent vials" not in str(spans["attributes"].tolist()).lower()


def test_inventory_question_skips_text2cypher(monkeypatch):
    def must_not_run(question):
        raise AssertionError("Text2Cypher should not run for inventory questions")

    monkeypatch.setattr(tenant_rag, "run_cypher", must_not_run)
    monkeypatch.setattr(llm, "client", lambda: fake_client("Morphine supply is listed in [H]."))
    with span("test_case") as case:
        result = tenant_rag.answer_for_user("northshore-pharmacist", "How many days of morphine do we have?")
    spans = trace_spans(case.trace_id)
    graph = spans.set_index("name").loc["graph_evidence"]
    assert graph["attributes"]["method"] == "ingredient_direct"
    assert graph["attributes"]["rows"] > 0
    assert len(result["inventory"]) > 0
    assert (spans["name"] == "llm").sum() == 1


def test_declined_text2cypher_falls_back_to_ingredient_lookup(monkeypatch):
    def not_answerable(question):
        raise NotAnswerable("forced for test")

    monkeypatch.setattr(tenant_rag, "run_cypher", not_answerable)
    monkeypatch.setattr(llm, "client", lambda: fake_client("Morphine shortage status is in [G]."))
    with span("test_case") as case:
        tenant_rag.answer_for_user("northshore-pharmacist", "Which morphine products are in shortage?")
    by_name = trace_spans(case.trace_id).set_index("name")
    graph = by_name.loc["graph_evidence"]
    assert graph["status"] == "ok"
    assert graph["attributes"]["method"] == "ingredient_fallback"
    for step in ("label_search", "tenant_evidence", "build_prompt"):
        assert step in by_name.index
    assert "rows_dropped" in by_name.loc["build_prompt", "attributes"]