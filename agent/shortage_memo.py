"""LangGraph agent: draft a shortage response memo from permitted evidence, validate it, and save it for approval."""
import json
import re
import sys
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import text

from retrieval.graph_rag import ANSWER_MODEL
from retrieval.llm import complete
from retrieval.private_search import query_private
from retrieval.tenant_rag import IDENTITY_SQL, INVENTORY_SQL
from tenancy.actions import create_action
from tenancy.db import user_session

MAX_ATTEMPTS = 2
URGENT_DAYS = 14
DRAFTING_ROLES = {"pharmacist", "procurement", "executive"}
REQUIRED_SECTIONS = ["## Situation", "## Supply runway", "## Protocol", "## Alternatives", "## Recommended actions"]
DRUGS_SQL = """
    select r.drug_rxcui, r.drug_name, r.risk_tier, r.risk_reasons, r.alternative_status,
           r.alternative_labeler_count, r.manufacturing_countries
    from analytics.mart_shortage_risk r
    join analytics.stg_drug_ingredients i on i.drug_rxcui = r.drug_rxcui
    where lower(i.ingredient_name) = :ingredient
"""
SYSTEM_PROMPT = """You draft shortage response memos for {tenant_name} pharmacy leadership.
Use ONLY the evidence provided. Every number you write must appear exactly in the evidence.
Risk tiers and alternative counts come from RxShield's analysis of public FDA data. Never attribute them to the FDA.
Every recommended action must cite the evidence it relies on. Do not introduce strategies the evidence does not support, such as preferring suppliers from a particular country.
In Supply runway, include every inventory item, ordered by days on hand from lowest to highest.
Substitution and conservation rules come only from hospital documents; cite them with [P1], [P2], ...
Use these exact section headings, in this order:
## Situation
## Supply runway
## Protocol
## Alternatives
## Recommended actions
Cite [R] for risk data, [H] for hospital inventory, and [P1], [P2], ... for hospital documents.
If the evidence for a section is missing, write "Not available in evidence."
Recommended actions must be concrete steps a pharmacist can take this week, grounded in the evidence.
This is a draft for human approval, not a final decision."""


class MemoState(TypedDict, total=False):
    user_id: str
    ingredient: str
    identity: dict
    evidence: dict
    draft: str
    problems: list
    attempts: int
    tokens: int
    action_id: int


def normalize(value):
    return re.sub(r"(?<=\d),(?=\d)", "", value.lower())


def check_draft(draft, evidence):
    evidence_text = normalize(json.dumps(evidence, default=str))
    clean_draft = normalize(draft)
    problems = [f"missing section '{s}'" for s in REQUIRED_SECTIONS if s not in draft]

    for number in set(re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])", draft)):
        clean = normalize(number)
        if len(clean) < 2 and "." not in clean:
            continue
        if not re.search(rf"(?<![\w.]){re.escape(clean)}(?![\w])", evidence_text):
            problems.append(f"number {number} does not appear in the evidence")

    for row in evidence.get("inventory", []):
        days = row.get("days_on_hand")
        units = str(row["on_hand_units"])
        if days is not None and float(days) <= URGENT_DAYS and \
                not re.search(rf"(?<![\w.]){re.escape(units)}(?![\w])", clean_draft):
            problems.append(f"urgent item missing: {row['drug_name']} has only {days} days on hand")

    if evidence.get("documents"):
        protocol = draft.split("## Protocol", 1)[-1].split("## Alternatives", 1)[0]
        if "not available" in protocol.lower() or "[P" not in protocol:
            problems.append("the Protocol section must summarize and cite the hospital documents [P1], [P2], ...")
    return problems


def gather(state):
    with user_session(state["user_id"]) as conn:
        identity = conn.execute(text(IDENTITY_SQL)).mappings().one_or_none()
        if identity is None or identity["role"] not in DRAFTING_ROLES:
            raise PermissionError("Only pharmacists, procurement, and executives can draft shortage memos.")
        drugs = [dict(r) for r in conn.execute(text(DRUGS_SQL), {"ingredient": state["ingredient"].lower()}).mappings()]
        rxcuis = [d["drug_rxcui"] for d in drugs]
        inventory = [dict(r) for r in conn.execute(text(INVENTORY_SQL), {"rxcuis": rxcuis}).mappings()] if rxcuis else []
        documents = query_private(conn, f"{state['ingredient']} shortage protocol", k=3)
    if not inventory:
        raise ValueError(f"{identity['tenant_name']} does not stock any {state['ingredient']} products in shortage.")
    evidence = {
        "risk": [d for d in drugs if d["drug_rxcui"] in {row["drug_rxcui"] for row in inventory}],
        "inventory": inventory,
        "documents": [{"id": f"P{i}", "title": d["title"], "content": d["content"]}
                      for i, d in enumerate(documents, start=1)],
    }
    return {"identity": dict(identity), "evidence": evidence, "attempts": 0, "tokens": 0}


def draft(state):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(**state["identity"])},
        {"role": "user", "content": f"Drug: {state['ingredient']}\n\nEvidence:\n"
                                    f"{json.dumps(state['evidence'], default=str, separators=(',', ':'))}"},
    ]
    if state.get("problems"):
        messages += [
            {"role": "assistant", "content": state["draft"]},
            {"role": "user", "content": "Fix these problems and return the full corrected memo:\n- "
                                        + "\n- ".join(state["problems"])},
        ]
    content, usage = complete(ANSWER_MODEL, messages)
    return {"draft": content, "attempts": state["attempts"] + 1,
            "tokens": state["tokens"] + usage["prompt_tokens"] + usage["completion_tokens"]}


def validate(state):
    return {"problems": check_draft(state["draft"], state["evidence"])}

def next_step(state):
    if not state["problems"]:
        return "save"
    return "redraft" if state["attempts"] < MAX_ATTEMPTS else "fail"


def save(state):
    evidence = state["evidence"]
    summary = {"drug_rxcuis": [r["drug_rxcui"] for r in evidence["inventory"]],
               "documents": [d["title"] for d in evidence["documents"]], "attempts": state["attempts"]}
    with user_session(state["user_id"]) as conn:
        action_id = create_action(conn, "shortage_response_memo",
                                  f"Shortage response: {state['ingredient']}", state["draft"], summary)
    return {"action_id": action_id}


def build_agent():
    graph = StateGraph(MemoState)
    graph.add_node("gather", gather)
    graph.add_node("draft", draft)
    graph.add_node("validate", validate)
    graph.add_node("save", save)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "draft")
    graph.add_edge("draft", "validate")
    graph.add_conditional_edges("validate", next_step, {"redraft": "draft", "save": "save", "fail": END})
    graph.add_edge("save", END)
    return graph.compile()


def draft_memo(user_id, ingredient):
    return build_agent().invoke({"user_id": user_id, "ingredient": ingredient})


def main():
    user_id, ingredient = sys.argv[1], sys.argv[2]
    try:
        state = draft_memo(user_id, ingredient)
    except (PermissionError, ValueError) as err:
        print(err)
        return
    print(state["draft"])
    print(f"\nattempts: {state['attempts']} | tokens: {state['tokens']} | problems: {state.get('problems') or 'none'}")
    if state.get("action_id"):
        print(f"Saved as action {state['action_id']}, pending approval")
    else:
        print("Not saved: the draft failed validation after the retry")


if __name__ == "__main__":
    main()