"""Cost-aware routing: label-only questions skip Text2Cypher; everything else gets full GraphRAG."""
import sys
import time

from dotenv import load_dotenv

from graph.db import get_driver
from observability.tracing import span
from retrieval import graph_rag
from retrieval.baseline_rag import SYSTEM_PROMPT as BASELINE_PROMPT
from retrieval.baseline_rag import build_context
from retrieval.cache import signature
from retrieval.graph_rag import ANSWER_MODEL, retrieve_label_chunks
from retrieval.llm import complete

load_dotenv(".env")

LABEL_INTENTS = {"storage", "contraindications", "boxed_warning", "dosing", "indications"}
SCOPE_RULE = ("\nState each fact only for the products whose sources say it. "
              "Never generalize to all products or preparations unless every source says so.")
LABEL_PROMPT = BASELINE_PROMPT + SCOPE_RULE
LABELS_FOR_INGREDIENTS = """
MATCH (d:Drug)-[:HAS_INGREDIENT]->(i:Ingredient) WHERE toLower(i.name) IN $ingredients
MATCH (d)<-[:IS_DRUG]-(:Package)-[:OF_PRODUCT]->(:Product)<-[:DESCRIBES]-(l:Label)
RETURN collect(DISTINCT l.spl_set_id) AS ids
"""


def choose_route(question):
    tokens = {t for t in signature(question).split("|") if t}
    drugs = sorted(t.split(":", 1)[1] for t in tokens if t.startswith("drug:"))
    intents = {t for t in tokens if not t.startswith("drug:")}
    if drugs and intents and intents <= LABEL_INTENTS:
        return "label", drugs
    return "graph", drugs


def answer_from_labels(question, ingredients, k=6):
    start = time.perf_counter()
    with span("label_lookup", ingredients=ingredients) as lookup:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(LABELS_FOR_INGREDIENTS, ingredients=ingredients)
        label_ids = records[0]["ids"]
        lookup.attributes["labels"] = len(label_ids)
    if not label_ids:
        return None

    with span("label_search", k=k) as search:
        chunks = retrieve_label_chunks(question, label_ids, k)
        search.attributes["chunks"] = len(chunks)
    content, usage = complete(ANSWER_MODEL, [
        {"role": "system", "content": LABEL_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nSources:\n{build_context(chunks)}"},
    ])
    return {
        "question": question, "answer": content, "sources": chunks, "label_ids": label_ids,
        "cypher": None, "model": ANSWER_MODEL, **usage,
        "total_ms": round((time.perf_counter() - start) * 1000),
    }


def answer_routed(question):
    with span("request", entry="answer_routed") as request:
        with span("route") as route_span:
            route, ingredients = choose_route(question)
            route_span.attributes.update(route=route, ingredients=ingredients)
        request.attributes.update(signature=signature(question), question_chars=len(question))
        if route == "label":
            result = answer_from_labels(question, ingredients)
            if result:
                request.attributes["route"] = "label"
                return {**result, "route": "label", "trace_id": request.trace_id}
            request.attributes["fallback"] = "no_labels"
        with span("graph_rag"):
            result = graph_rag.answer(question)
        request.attributes["route"] = "graph"
        return {**result, "route": "graph", "trace_id": request.trace_id}


def main():
    question = " ".join(sys.argv[1:])
    route, ingredients = choose_route(question)
    print(f"Route: {route} | ingredients: {ingredients} | signature: {signature(question)}")
    result = answer_routed(question)
    print(f"\n{result['answer']}\n\n[{result['route']} route, "
          f"{result['prompt_tokens'] + result['completion_tokens']} tokens, {result['total_ms']} ms]")
    print(f"trace: {result['trace_id']}")


if __name__ == "__main__":
    main()