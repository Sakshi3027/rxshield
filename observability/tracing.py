"""Request tracing: nested, timed spans written to ops.spans."""
import contextvars
import json
import time
import uuid
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import text

from tenancy.db import get_app_engine

INSERT_SQL = text("""
    insert into ops.spans (span_id, trace_id, parent_id, name, started_at,
                           duration_ms, status, error_type, attributes)
    values (:span_id, :trace_id, :parent_id, :name, :started_at,
            :duration_ms, :status, :error_type, cast(:attributes as jsonb))
""")

_current = contextvars.ContextVar("rxshield_span", default=None)


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    attributes: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def _engine():
    return get_app_engine()


def current_ids():
    current = _current.get()
    return (current.trace_id, current.span_id) if current else (None, None)


def _write(current, started_at, duration_ms, status, error_type):
    try:
        with _engine().begin() as conn:
            conn.execute(INSERT_SQL, {
                "span_id": current.span_id,
                "trace_id": current.trace_id,
                "parent_id": current.parent_id,
                "name": current.name,
                "started_at": started_at,
                "duration_ms": duration_ms,
                "status": status,
                "error_type": error_type,
                "attributes": json.dumps(current.attributes, default=str),
            })
    except Exception as exc:
        warnings.warn(f"span {current.name} not recorded: {type(exc).__name__}")


@contextmanager
def span(name, denied=(), **attributes):
    refusals = (PermissionError, *denied)
    parent = _current.get()
    current = Span(
        trace_id=parent.trace_id if parent else uuid.uuid4().hex,
        span_id=uuid.uuid4().hex[:16],
        parent_id=parent.span_id if parent else None,
        name=name,
        attributes=dict(attributes),
    )
    token = _current.set(current)
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    status, error_type = "ok", None
    try:
        yield current
    except refusals as exc:
        status, error_type = "denied", type(exc).__name__
        raise
    except Exception as exc:
        status, error_type = "error", type(exc).__name__
        raise
    finally:
        _current.reset(token)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        _write(current, started_at, duration_ms, status, error_type)