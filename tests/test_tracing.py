import uuid

import pandas as pd
import pytest
from sqlalchemy import exc, text

from ingestion.db import get_engine
from observability.tracing import current_ids, span
from tenancy.db import user_session


def fetch(trace_id):
    with get_engine().connect() as conn:
        return pd.read_sql(text("select * from ops.spans where trace_id = :t"),
                           conn, params={"t": trace_id})


def test_nested_spans_share_a_trace():
    with span("test_request", route="label") as outer:
        with span("test_child") as inner:
            assert current_ids() == (outer.trace_id, inner.span_id)
    assert current_ids() == (None, None)
    rows = fetch(outer.trace_id).set_index("name")
    assert len(rows) == 2
    assert rows.loc["test_child", "parent_id"] == outer.span_id
    assert pd.isna(rows.loc["test_request", "parent_id"])
    assert rows.loc["test_request", "attributes"] == {"route": "label"}


def test_errors_record_type_but_never_message():
    secret = f"password={uuid.uuid4().hex}"
    with pytest.raises(ValueError, match="password="):
        with span("test_failing") as failing:
            raise ValueError(secret)
    row = fetch(failing.trace_id).iloc[0]
    assert row["status"] == "error"
    assert row["error_type"] == "ValueError"
    assert secret not in row.to_json()


def test_permission_errors_are_denied_not_errors():
    with pytest.raises(PermissionError):
        with span("test_denied") as denied:
            raise PermissionError("role cannot run simulation")
    assert fetch(denied.trace_id).iloc[0]["status"] == "denied"


def test_app_cannot_read_traces():
    with pytest.raises(exc.ProgrammingError, match="permission denied"):
        with user_session("northshore-pharmacist") as conn:
            conn.execute(text("select count(*) from ops.spans"))

class QuotaHit(Exception):
    pass


def test_listed_refusals_are_denied():
    with pytest.raises(QuotaHit):
        with span("test_quota", denied=(QuotaHit,)) as limited:
            raise QuotaHit("slow down")
    row = fetch(limited.trace_id).iloc[0]
    assert row["status"] == "denied"
    assert row["error_type"] == "QuotaHit"