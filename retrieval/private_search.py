"""Permission-aware retrieval over private hospital documents, filtered by the database and audited."""
from sqlalchemy import text

from retrieval.embed_labels import SEARCH_PATH
from retrieval.vector_search import embed_query
from tenancy.audit import log_access
from tenancy.db import user_session


def query_private(conn, question, k=4):
    conn.execute(text(SEARCH_PATH))
    rows = conn.execute(text("""
        select chunk_id, tenant_id, doc_type, title, content,
               1 - (embedding <=> cast(:q as vector)) as similarity
        from rag.tenant_chunks
        order by embedding <=> cast(:q as vector)
        limit :k"""), {"q": embed_query(question), "k": k}).mappings().all()
    return [dict(row) for row in rows]


def search_private(user_id, question, k=4):
    with user_session(user_id) as conn:
        results = query_private(conn, question, k)
        log_access(conn, "private_search", question, [r["chunk_id"] for r in results])
    return results