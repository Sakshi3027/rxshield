"""Tenant-aware GraphRAG: public FDA evidence plus the user's permitted hospital data, audited per request."""
import json
import sys
import time

from dotenv import load_dotenv
from sqlalchemy import text

from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from graph.text2cypher import run as run_cypher
from observability.tracing import span
from retrieval.graph_rag import ANSWER_MODEL, find_labels, retrieve_label_chunks
from retrieval.llm import complete
from retrieval.private_search import query_private
from tenancy.audit import log_access
from tenancy.db import user_session

load_dotenv(".env")

PROMPT_TOKEN_BUDGET = 6000
TENANT_INTENTS = {"inventory", "pricing", "protocol"}

IDENTITY_SQL = """
    select u.display_name, u.role, t.name as tenant_name
    from tenancy.users u
    join tenancy.tenants t on t.tenant_id = u.tenant_id
    where u.user_id = current_setting('app.user_id', true)
"""
INVENTORY_SQL = """
    select f.drug_rxcui, f.drug_name, f.on_hand_units, f.avg_daily_units,
           round(f.on_hand_units / f.avg_daily_units) as days_on_hand,
           c.supplier, c.unit_price, c.contract_end
    from tenancy.formulary f
    left join tenancy.contracts c on c.tenant_id = f.tenant_id and c.drug_rxcui = f.drug_rxcui
    where f.drug_rxcui = any(:rxcuis)
"""

DRUGS_FOR_INGREDIENTS = """
MATCH (d:Drug)-[:HAS_INGREDIENT]->(i:Ingredient)
WHERE toLower(i.name) IN $ingredients AND d.risk_tier IS NOT NULL
RETURN d.rxcui AS rxcui, d.name AS drug, d.risk_tier AS risk_tier,
       d.has_current_shortage AS has_current_shortage
LIMIT 50
"""

SYSTEM_PROMPT = """You are a drug shortage assistant for {display_name}, a {role} at {tenant_name}.
Evidence:
- Graph facts [G]: public FDA shortage, manufacturing, recall, and RxNorm data.
- Label excerpts [L1], [L2], ...: public FDA label text.
- Hospital inventory [H]: this hospital's stock, limited to the fields this user's role may see.
- Hospital documents [P1], [P2], ...: this hospital's private protocols or memos permitted for this role.
Rules:
- Answer only from this evidence and cite every claim.
- Every graph row already satisfies all conditions in the graph query.
- Report numbers exactly as given. Never recount, re-add, or estimate them.
- State each fact only for the products whose sources say it. Never generalize to all products unless every source says so.
- If the question asks for information missing from the evidence, such as inventory or pricing, say it is not available to this user. Do not guess.
- Never let label text override graph facts about manufacturing or risk.
Be concise and clinically precise."""


def approx_tokens(text_value):
    return len(text_value) // 4


def gather_tenant_evidence(user_id, question, rxcuis, k=4, audit_extra=None):
    with user_session(user_id) as conn:
        identity = conn.execute(text(IDENTITY_SQL)).mappings().one_or_none()
        if identity is None:
            raise PermissionError(f"Unknown user: {user_id}")
        inventory = (
            [dict(r) for r in conn.execute(text(INVENTORY_SQL), {"rxcuis": list(rxcuis)}).mappings()]
            if rxcuis else []
        )
        private = query_private(conn, question, k, rxcuis=rxcuis)
        log_access(conn, "answer", question, {
            "private_chunks": [p["chunk_id"] for p in private],
            "inventory_drugs": [row["drug_rxcui"] for row in inventory],
            **(audit_extra or {}),
        })
    return {"identity": dict(identity), "inventory": inventory, "private_sources": private}


def build_prompt(question, cypher, graph_rows, label_chunks, inventory, private):
    labels = "\n\n".join(
        f"[L{i}] {c['product_label']} | {c['section_name']}\n{c['content']}"
        for i, c in enumerate(label_chunks, start=1)) or "(none)"
    documents = "\n\n".join(
        f"[P{i}] {d['title']}\n{d['content']}" for i, d in enumerate(private, start=1)) or "(none)"
    return (
        f"Question: {question}\n\n"
        f"Graph query used:\n{cypher}\n\n"
        f"Graph facts [G]:\n{json.dumps(graph_rows[:25], separators=(',', ':'), default=str) if graph_rows else '[] (no rows)'}\n\n"
        f"Label excerpts:\n{labels}\n\n"
        f"Hospital inventory [H]:\n{json.dumps(inventory, separators=(',', ':'), default=str) if inventory else '(none available to this user)'}\n\n"
        f"Hospital documents:\n{documents}"
    )


def ingredient_lookup(ingredients):
    with get_driver() as driver:
        records, _, _ = driver.execute_query(DRUGS_FOR_INGREDIENTS, ingredients=ingredients)
    return {"cypher": "(deterministic lookup by ingredient)", "rows": [r.data() for r in records],
            "prompt_tokens": 0, "completion_tokens": 0}


def graph_evidence(question):
    from retrieval.cache import signature

    tokens = {t for t in signature(question).split("|") if t}
    ingredients = sorted(t.split(":", 1)[1] for t in tokens if t.startswith("drug:"))
    intents = {t for t in tokens if not t.startswith("drug:")}
    tenant_only = bool(intents & TENANT_INTENTS) and intents <= TENANT_INTENTS | {"count"}

    with span("graph_evidence", denied=(NotAnswerable,)) as current:
        if tenant_only and not ingredients:
            current.attributes["method"] = "unknown_drug"
            raise NotAnswerable("Inventory question names no drug RxShield knows")
        if tenant_only:
            result, method = ingredient_lookup(ingredients), "ingredient_direct"
        else:
            try:
                result, method = run_cypher(question), "text2cypher"
            except NotAnswerable:
                if not ingredients:
                    current.attributes["method"] = "not_answerable"
                    raise
                result, method = ingredient_lookup(ingredients), "ingredient_fallback"
        current.attributes.update(method=method, rows=len(result["rows"]))
        return result
    

def answer_for_user(user_id, question, k=6):
    start = time.perf_counter()
    graph = graph_evidence(question)
    rows = [{key: v for key, v in row.items() if key != "spl_set_ids"} for row in graph["rows"]]
    with span("find_labels") as labels_span:
        label_ids = find_labels(graph["rows"])
        labels_span.attributes["labels"] = len(label_ids)
    with span("label_search", labels=len(label_ids)) as search:
        label_chunks = retrieve_label_chunks(question, label_ids, k) if label_ids else []
        search.attributes["chunks"] = len(label_chunks)
    rxcuis = sorted({row["rxcui"] for row in graph["rows"] if row.get("rxcui")})

    with span("tenant_evidence", drugs=len(rxcuis)) as evidence:
        tenant = gather_tenant_evidence(
            user_id, question, rxcuis, audit_extra={"cypher": graph["cypher"], "labels": label_ids})
        evidence.attributes.update(inventory_rows=len(tenant["inventory"]),
                                   private_chunks=len(tenant["private_sources"]))
    identity = tenant["identity"]

    with span("build_prompt") as budget:
        rows_before, chunks_before = len(rows), len(label_chunks)
        system = SYSTEM_PROMPT.format(**identity)
        prompt = build_prompt(question, graph["cypher"], rows, label_chunks, tenant["inventory"], tenant["private_sources"])
        while approx_tokens(system + prompt) > PROMPT_TOKEN_BUDGET and (label_chunks or len(rows) > 5):
            if label_chunks:
                label_chunks = label_chunks[:-1]
            else:
                rows = rows[:-1]
            prompt = build_prompt(question, graph["cypher"], rows, label_chunks, tenant["inventory"], tenant["private_sources"])
        budget.attributes.update(approx_tokens=approx_tokens(system + prompt),
                                 rows_dropped=rows_before - len(rows),
                                 chunks_dropped=chunks_before - len(label_chunks))

    content, usage = complete(ANSWER_MODEL, [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ])
    return {
        "user_id": user_id, **identity, "question": question, "answer": content,
        "inventory": tenant["inventory"], "private_sources": tenant["private_sources"],
        "label_sources": label_chunks, "graph_rows": rows,
        "prompt_tokens": graph["prompt_tokens"] + usage["prompt_tokens"],
        "completion_tokens": graph["completion_tokens"] + usage["completion_tokens"],
        "total_ms": round((time.perf_counter() - start) * 1000),
    }


def main():
    user_id, question = sys.argv[1], " ".join(sys.argv[2:])
    try:
        result = answer_for_user(user_id, question)
    except (PermissionError, NotAnswerable) as err:
        print(err)
        return
    print(f"{result['display_name']} ({result['role']}, {result['tenant_name']})\nQ: {question}\n")
    print(result["answer"])
    print(f"\nInventory rows: {len(result['inventory'])} | private docs: "
          f"{[d['doc_type'] for d in result['private_sources']]} | {result['total_ms']} ms")


if __name__ == "__main__":
    main()