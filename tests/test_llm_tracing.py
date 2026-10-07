from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import text

from ingestion.db import get_engine
from observability.tracing import span
from retrieval import llm


def fake_client(content, finish_reason):
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
    )
    completions = SimpleNamespace(create=lambda **kwargs: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def fetch(table, trace_id):
    with get_engine().connect() as conn:
        return pd.read_sql(text(f"select * from ops.{table} where trace_id = :t"),
                           conn, params={"t": trace_id})


def test_llm_call_is_stamped_with_its_trace(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake_client("Answer.", "stop"))
    with span("test_request") as request:
        content, usage = llm.complete("test-model", [{"role": "user", "content": "hi"}])
    assert content == "Answer."
    llm_span = fetch("spans", request.trace_id).set_index("name").loc["llm"]
    assert llm_span["parent_id"] == request.span_id
    assert llm_span["attributes"]["prompt_tokens"] == 11
    call = fetch("llm_calls", request.trace_id).iloc[0]
    assert call["span_id"] == llm_span["span_id"]
    assert call["succeeded"]


def test_truncated_answer_is_a_traced_error(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake_client("Partial", "length"))
    with pytest.raises(llm.EmptyCompletion):
        with span("test_request") as request:
            llm.complete("test-model", [{"role": "user", "content": "hi"}])
    llm_span = fetch("spans", request.trace_id).set_index("name").loc["llm"]
    assert llm_span["status"] == "error"
    assert llm_span["error_type"] == "EmptyCompletion"
    call = fetch("llm_calls", request.trace_id).iloc[0]
    assert call["attempts"] == 2
    assert call["prompt_tokens"] == 22
    assert not call["succeeded"]

def test_capture_collects_calls_only_inside_the_block(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake_client("Answer.", "stop"))
    with llm.capture_calls() as calls:
        llm.complete("test-model", [{"role": "user", "content": "hi"}])
    llm.complete("test-model", [{"role": "user", "content": "outside"}])
    assert len(calls) == 1
    assert calls[0]["content"] == "Answer."
    assert calls[0]["messages"][-1]["content"] == "hi"

def test_fullwidth_citation_brackets_are_normalized(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake_client("Stock covers 12 days【H】【P1】.", "stop"))
    content, _ = llm.complete("test-model", [{"role": "user", "content": "hi"}])
    assert content == "Stock covers 12 days[H][P1]."