"""Synthetic hospital documents must stay clinically plausible."""
from sqlalchemy import text

from ingestion.db import get_engine


def test_no_oral_conversion_for_drugs_without_an_oral_form():
    with get_engine().connect() as conn:
        protocols = conn.execute(text(
            "select content from rag.tenant_chunks "
            "where doc_type = 'protocol' and title ilike '%rocuronium%'")).scalars().all()
    assert protocols
    assert not any("oral route" in p.lower() for p in protocols)