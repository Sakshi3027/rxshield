import pytest
from sqlalchemy import text

from ingestion.db import get_engine
from observability import writer


@pytest.fixture(autouse=True, scope="session")
def clean_test_telemetry():
    writer.set_synchronous(True)
    yield
    with get_engine().begin() as conn:
        conn.execute(text("""
            delete from ops.llm_calls where model = 'test-model' or trace_id in
                (select trace_id from ops.spans where name like 'test\\_%')"""))
        conn.execute(text("""
            delete from ops.spans where trace_id in
                (select trace_id from ops.spans where name like 'test\\_%')"""))
        conn.execute(text("""
            delete from ops.spans where trace_id in
                (select trace_id from ops.spans where name = 'http' and attributes->>'path' like '/\\_test/%')"""))