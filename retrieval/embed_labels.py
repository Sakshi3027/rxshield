"""Chunk FDA label sections, embed them, and store them in pgvector (rag.label_chunks)."""
import numpy as np
import pandas as pd
from fastembed import TextEmbedding
from sqlalchemy import text
from tqdm import tqdm

from ingestion.db import get_engine

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CHUNK_CHARS = 1500
OVERLAP_CHARS = 200
INSERT_BATCH = 500
SEARCH_PATH = "set local search_path to rag, extensions, public"


def chunk_text(content):
    if len(content) <= CHUNK_CHARS:
        return [content]
    chunks, start = [], 0
    while start < len(content):
        end = min(start + CHUNK_CHARS, len(content))
        if end < len(content):
            cut = content.rfind(". ", start + CHUNK_CHARS // 2, end)
            if cut != -1:
                end = cut + 1
        chunks.append(content[start:end].strip())
        if end == len(content):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return chunks


def build_chunks(sections):
    rows = []
    for s in sections.itertuples():
        for i, chunk in enumerate(chunk_text(s.text)):
            rows.append({
                "chunk_id": f"{s.section_id}|{i}",
                "section_id": s.section_id,
                "spl_set_id": s.spl_set_id,
                "product_label": s.product_label,
                "section_name": s.section_name,
                "chunk_index": i,
                "content": chunk,
                "embed_text": f"{s.product_label} | {s.section_name}: {chunk}",
            })
    return pd.DataFrame(rows)


def to_vector(values):
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"

def embed(model, texts):
    vectors = np.array(list(tqdm(model.embed(texts, batch_size=64, parallel=0), total=len(texts), desc="Embedding")))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

def main():
    engine = get_engine()
    sections = pd.read_sql("select * from silver.spl_sections", engine)
    chunks = build_chunks(sections)
    print(f"{len(sections)} sections -> {len(chunks)} chunks")

    print(f"Embedding with {MODEL_NAME} (a few minutes)")
    model = TextEmbedding(MODEL_NAME)
    embeddings = embed(model, chunks["embed_text"].tolist())
    chunks["embedding"] = [to_vector(e) for e in embeddings]

    with engine.begin() as conn:
        conn.execute(text("create schema if not exists rag"))
        conn.execute(text(SEARCH_PATH))
        conn.execute(text("drop table if exists rag.label_chunks cascade"))
        conn.execute(text(f"""
            create table rag.label_chunks (
                chunk_id text primary key,
                section_id text not null,
                spl_set_id text not null,
                product_label text,
                section_name text,
                chunk_index int,
                content text not null,
                embedding vector({embeddings.shape[1]}) not null
            )"""))

    records = chunks.drop(columns=["embed_text"]).to_dict("records")
    insert = text("""
        insert into rag.label_chunks
            (chunk_id, section_id, spl_set_id, product_label, section_name, chunk_index, content, embedding)
        values
            (:chunk_id, :section_id, :spl_set_id, :product_label, :section_name, :chunk_index, :content,
             cast(:embedding as vector))""")
    for start in range(0, len(records), INSERT_BATCH):
        with engine.begin() as conn:
            conn.execute(text(SEARCH_PATH))
            conn.execute(insert, records[start:start + INSERT_BATCH])
    print(f"Inserted {len(records)} chunks")

    with engine.begin() as conn:
        conn.execute(text(SEARCH_PATH))
        conn.execute(text(
            "create index label_chunks_embedding_idx on rag.label_chunks "
            "using hnsw (embedding vector_cosine_ops)"))
        count = conn.execute(text("select count(*) from rag.label_chunks")).scalar()
    print(f"Index built, {count} rows in rag.label_chunks")

    question = "How should bupivacaine vials be stored?"
    query_vector = to_vector(embed(model, [QUERY_PREFIX + question])[0])
    with engine.begin() as conn:
        conn.execute(text(SEARCH_PATH))
        results = conn.execute(text("""
            select product_label, section_name, left(content, 100) as preview,
                   round((1 - (embedding <=> cast(:q as vector)))::numeric, 3) as similarity
            from rag.label_chunks
            order by embedding <=> cast(:q as vector)
            limit 3"""), {"q": query_vector}).fetchall()
    print(f"\nSmoke test: {question}")
    for row in results:
        print(f"  {row.similarity}  {row.product_label} | {row.section_name}: {row.preview}")


if __name__ == "__main__":
    main()