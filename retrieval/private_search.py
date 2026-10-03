"""Permission-aware retrieval over private hospital documents, filtered by the database and audited."""
from sqlalchemy import text

from retrieval.embed_labels import SEARCH_PATH
from retrieval.vector_search import embed_query
from tenancy.audit import log_access
from tenancy.db import user_session


def search_private(user_id, question, k=4):
    query_vector = embed_query(question)
    with user_session(user_id) as conn:
        conn.execute(text(SEARCH_PATH))
        rows = conn.execute(text("""
            select chunk_id, tenant_id, doc_type, title, content,
                   1 - (embedding <=> cast(:q as vector)) as similarity
            from rag.tenant_chunks
            order by embedding <=> cast(:q as vector)
            limit :k"""), {"q": query_vector, "k": k}).mappings().all()
        results = [dict(row) for row in rows]
        log_access(conn, "private_search", question, [r["chunk_id"] for r in results])
    return results