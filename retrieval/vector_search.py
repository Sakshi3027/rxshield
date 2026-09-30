"""Vector search over FDA label chunks in pgvector."""
from functools import lru_cache

import numpy as np
import re
from fastembed import TextEmbedding
from sqlalchemy import text

from ingestion.db import get_engine
from retrieval.embed_labels import MODEL_NAME, QUERY_PREFIX, SEARCH_PATH, to_vector

SECTION_HINTS = [
    (r"\bboxed warning", ["Boxed Warning"]),
    (r"\bcontraindicat", ["Contraindications"]),
    (r"\bindicat|\bused for\b", ["Indications and Usage"]),
    (r"\bstor(e|ed|age|ing)\b", ["How Supplied / Storage and Handling"]),
    (r"\bdos(e|es|ing|age)\b", ["Dosage and Administration", "Dosage Forms and Strengths"]),
    (r"\binteract", ["Drug Interactions"]),
    (r"\bwarnings?\b|\bprecaution", ["Warnings and Precautions", "Warnings", "Precautions"]),
]


def detect_sections(question):
    text_lower = question.lower()
    sections = []
    for pattern, names in SECTION_HINTS:
        if re.search(pattern, text_lower):
            sections += [n for n in names if n not in sections]
            text_lower = re.sub(pattern, " ", text_lower)
    return sections


@lru_cache(maxsize=1)
def get_model():
    return TextEmbedding(MODEL_NAME)


@lru_cache(maxsize=1)
def get_cached_engine():
    return get_engine()


def embed_query(question):
    vector = np.array(list(get_model().embed([QUERY_PREFIX + question])))[0]
    return to_vector(vector / np.linalg.norm(vector))


def search(question, k=6, spl_set_ids=None, sections=None):
    params = {"q": embed_query(question), "k": k}
    filters = []
    if spl_set_ids:
        filters.append("spl_set_id = any(:ids)")
        params["ids"] = list(spl_set_ids)
    if sections:
        filters.append("section_name = any(:sections)")
        params["sections"] = list(sections)

    if filters:
        sql = f"""
            with candidates as materialized (
                select chunk_id, spl_set_id, product_label, section_name, content,
                       embedding <=> cast(:q as vector) as distance
                from rag.label_chunks
                where {' and '.join(filters)}
            )
            select chunk_id, spl_set_id, product_label, section_name, content,
                   1 - distance as similarity
            from candidates
            order by distance
            limit :k"""
    else:
        sql = """
            select chunk_id, spl_set_id, product_label, section_name, content,
                   1 - (embedding <=> cast(:q as vector)) as similarity
            from rag.label_chunks
            order by embedding <=> cast(:q as vector)
            limit :k"""

    with get_cached_engine().begin() as conn:
        conn.execute(text(SEARCH_PATH))
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]