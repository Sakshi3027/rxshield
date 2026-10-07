import pandas as pd
import pytest
from sqlalchemy import text

from graph.text2cypher import NotAnswerable
from ingestion.db import get_engine
from observability import writer
from observability.tracing import span
from retrieval import tenant_rag


def test_background_writer_records_after_flush():
    writer.set_synchronous(False)
    try:
        with span("test_async") as recorded:
            pass
        writer.flush()
    finally:
        writer.set_synchronous(True)
    with get_engine().connect() as conn:
        spans = pd.read_sql(text("select name from ops.spans where trace_id = :t"),
                            conn, params={"t": recorded.trace_id})
    assert spans["name"].tolist() == ["test_async"]


def test_unknown_drug_in_inventory_question_fails_fast(monkeypatch):
    def must_not_run(question):
        raise AssertionError("Text2Cypher should not run for an unrecognized drug")

    monkeypatch.setattr(tenant_rag, "run_cypher", must_not_run)
    with pytest.raises(NotAnswerable):
        tenant_rag.graph_evidence("How many days of zorblatin do we have?")