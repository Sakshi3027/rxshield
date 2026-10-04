"""Prove the cache never matches different entities, and never crosses tenant or role boundaries."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from evals.cache_similarity import PAIRS
from ingestion.db import get_engine
from retrieval.cache import current_data_version, lookup, signature, store
from retrieval.vector_search import embed_query
from tenancy.db import user_session

ENTITY_SWAPS = [pair for pair in PAIRS if pair[0] == "entity_swap"]


@pytest.mark.parametrize("kind, a, b", ENTITY_SWAPS)
def test_entity_swaps_never_share_a_signature(kind, a, b):
    assert signature(a) != signature(b)


def test_paraphrases_and_brand_names_share_a_signature():
    assert signature("Which critical shortage drugs are made only in India?") == \
        signature("What critical drugs in shortage are manufactured exclusively in India?")
    assert signature("How should Nipent vials be stored?") == \
        signature("What are the storage requirements for pentostatin vials?")


@pytest.fixture
def cached_entry():
    question = f"TEST cache entry {uuid.uuid4()}"
    vector = embed_query(question)
    with user_session("northshore-pharmacist") as conn:
        version = current_data_version(conn)
        store(conn, question, "test:sig", vector, {"answer": "cached"}, version)
    yield vector, version
    with get_engine().begin() as conn:
        conn.execute(text("delete from rag.answer_cache where question like 'TEST cache entry %'"))


@pytest.mark.parametrize("user, visible", [
    ("northshore-pharmacist", True),
    ("northshore-clinician", False),
    ("sunbelt-pharmacist", False),
])
def test_cache_entries_are_scoped_to_tenant_and_role(cached_entry, user, visible):
    vector, version = cached_entry
    with user_session(user) as conn:
        hit = lookup(conn, "test:sig", vector, version)
    assert (hit is not None) == visible


def test_app_cannot_poison_another_scope():
    vector = embed_query("poison attempt")
    with pytest.raises(DBAPIError, match="row-level security"):
        with user_session("northshore-pharmacist") as conn:
            conn.execute(text(
                "insert into rag.answer_cache "
                "(scope_tenant, scope_role, signature, question, embedding, answer, data_version) "
                "values ('sunbelt', 'pharmacist', 'x', 'TEST cache entry poison', "
                "cast(:q as extensions.vector), cast('{}' as jsonb), 'v')"), {"q": vector})