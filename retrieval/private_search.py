"""Permission-aware retrieval over private hospital documents, filtered by the database and audited."""
from sqlalchemy import text

from retrieval.embed_labels import SEARCH_PATH
from retrieval.vector_search import embed_query
from tenancy.audit import log_access
from tenancy.db import user_session

ANY_DOCUMENT_SQL = text("""
    select chunk_id, tenant_id, doc_type, title, content,
           1 - (embedding <=> cast(:q as vector)) as similarity
    from rag.tenant_chunks
    order by embedding <=> cast(:q as vector)
    limit :k""")

DRUG_DOCUMENT_SQL = text("""
    with candidates as materialized (
        select chunk_id, tenant_id, doc_type, title, content, embedding
        from rag.tenant_chunks
        where drug_rxcui = any(:rxcuis)
    )
    select chunk_id, tenant_id, doc_type, title, content,
           1 - (embedding <=> cast(:q as vector)) as similarity
    from candidates
    order by embedding <=> cast(:q as vector)
    limit :k""")


def query_private(conn, question, k=4, rxcuis=None):
    conn.execute(text(SEARCH_PATH))
    params = {"q": embed_query(question), "k": k}
    if rxcuis:
        rows = conn.execute(DRUG_DOCUMENT_SQL, {**params, "rxcuis": list(rxcuis)}).mappings().all()
    else:
        rows = conn.execute(ANY_DOCUMENT_SQL, params).mappings().all()
    return [dict(row) for row in rows]


def search_private(user_id, question, k=4):
    with user_session(user_id) as conn:
        results = query_private(conn, question, k)
        log_access(conn, "private_search", question, [r["chunk_id"] for r in results])
    return results