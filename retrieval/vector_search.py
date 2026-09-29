"""Vector search over FDA label chunks in pgvector."""
from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding
from sqlalchemy import text

from ingestion.db import get_engine
from retrieval.embed_labels import MODEL_NAME, QUERY_PREFIX, SEARCH_PATH, to_vector


@lru_cache(maxsize=1)
def get_model():
    return TextEmbedding(MODEL_NAME)


@lru_cache(maxsize=1)
def get_cached_engine():
    return get_engine()


def embed_query(question):
    vector = np.array(list(get_model().embed([QUERY_PREFIX + question])))[0]
    return to_vector(vector / np.linalg.norm(vector))


def search(question, k=6, spl_set_ids=None):
    query_vector = embed_query(question)
    label_filter = "where spl_set_id = any(:ids)" if spl_set_ids else ""
    sql = f"""
        with candidates as materialized (
            select chunk_id, spl_set_id, product_label, section_name, content,
                   embedding <=> cast(:q as vector) as distance
            from rag.label_chunks
            {label_filter}
        )
        select chunk_id, spl_set_id, product_label, section_name, content,
               1 - distance as similarity
        from candidates
        order by distance
        limit :k"""
    params = {"q": query_vector, "k": k}
    if spl_set_ids:
        params["ids"] = list(spl_set_ids)
        with get_cached_engine().begin() as conn:
            conn.execute(text(SEARCH_PATH))
            rows = conn.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

    with get_cached_engine().begin() as conn:
        conn.execute(text(SEARCH_PATH))
        rows = conn.execute(text("""
            select chunk_id, spl_set_id, product_label, section_name, content,
                   1 - (embedding <=> cast(:q as vector)) as similarity
            from rag.label_chunks
            order by embedding <=> cast(:q as vector)
            limit :k"""), params).mappings().all()
    return [dict(row) for row in rows]