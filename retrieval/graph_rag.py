"""GraphRAG: the knowledge graph finds which drugs, label search explains them, an LLM answers from both."""
import json
import os
import sys
import time

from dotenv import load_dotenv
from groq import Groq

from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from graph.text2cypher import run as run_cypher
from retrieval.vector_search import search

load_dotenv(".env")

ANSWER_MODEL = "openai/gpt-oss-20b"
MAX_GRAPH_ROWS = 25
LABEL_LOOKUP = """
MATCH (d:Drug) WHERE d.rxcui IN $rxcuis
MATCH (d)<-[:IS_DRUG]-(:Package)-[:OF_PRODUCT]->(:Product)<-[:DESCRIBES]-(l:Label)
RETURN collect(DISTINCT l.spl_set_id) AS spl_set_ids
"""
SYSTEM_PROMPT = """You are a drug shortage assistant for hospital pharmacists.
You receive two kinds of evidence:
- Graph facts [G]: results of a query over FDA shortage, manufacturing, recall, and RxNorm data.
  These are authoritative for which drugs are affected, risk tiers, where drugs are made, alternatives, and recalls.
- Label excerpts [1], [2], ...: FDA label text. Use these for clinical content such as storage, dosing,
  warnings, contraindications, and indications.
Rules:
- Answer only from this evidence. Cite graph facts with [G] and label excerpts with their numbers.
- Every graph row already satisfies all conditions in the graph query, so treat those conditions as facts about each row.
- If the graph facts are empty, say no matching drugs were found. Do not substitute other drugs.
- Never let label text override graph facts about manufacturing or risk.
- If something the question asks is not in the evidence, say what is missing.
Be concise and clinically precise."""


def find_labels(rows):
    label_ids = {sid for row in rows for sid in (row.get("spl_set_ids") or [])}
    rxcuis = [row["rxcui"] for row in rows if row.get("rxcui")]
    if rxcuis:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(LABEL_LOOKUP, rxcuis=rxcuis)
        label_ids.update(records[0]["spl_set_ids"])
    return sorted(label_ids)


def build_prompt(question, cypher, graph_rows, chunks):
    graph_text = (
        json.dumps(graph_rows[:MAX_GRAPH_ROWS], indent=1, default=str)
        if graph_rows else "[] (the graph query returned no matching rows)"
    )
    label_text = "\n\n".join(
        f"[{i}] {c['product_label']} | {c['section_name']}\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    ) or "(no label excerpts)"
    return (
        f"Question: {question}\n\n"
        f"Graph query used:\n{cypher}\n\n"
        f"Graph facts [G]:\n{graph_text}\n\n"
        f"Label excerpts:\n{label_text}"
    )


def answer(question, k=6):
    start = time.perf_counter()
    graph = run_cypher(question)
    rows = [{key: value for key, value in row.items() if key != "spl_set_ids"} for row in graph["rows"]]

    label_ids = find_labels(graph["rows"])
    chunks = search(question, k=k, spl_set_ids=label_ids) if label_ids else []

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=ANSWER_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(question, graph["cypher"], rows, chunks)},
        ],
    )
    return {
        "question": question,
        "answer": response.choices[0].message.content,
        "cypher": graph["cypher"],
        "graph_rows": rows,
        "label_ids": label_ids,
        "sources": chunks,
        "model": ANSWER_MODEL,
        "prompt_tokens": graph["prompt_tokens"] + response.usage.prompt_tokens,
        "completion_tokens": graph["completion_tokens"] + response.usage.completion_tokens,
        "total_ms": round((time.perf_counter() - start) * 1000),
    }


def main():
    question = " ".join(sys.argv[1:]) or "Which critical shortage drugs are made only in India, and how should they be stored?"
    try:
        result = answer(question)
    except (PermissionError, NotAnswerable) as err:
        print(err)
        return
    print(f"Q: {result['question']}\n")
    print(result["answer"])
    print(f"\nGraph: {len(result['graph_rows'])} rows | labels searched: {len(result['label_ids'])}")
    for i, chunk in enumerate(result["sources"], start=1):
        print(f"  [{i}] {chunk['similarity']:.3f}  {chunk['product_label']} | {chunk['section_name']}")
    print(f"\n{result['prompt_tokens']} in / {result['completion_tokens']} out tokens | total {result['total_ms']} ms")


if __name__ == "__main__":
    main()