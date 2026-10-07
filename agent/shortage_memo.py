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
from tenancy.actions import create_action, get_action
from tenancy.db import user_session

MAX_ATTEMPTS = 2
URGENT_DAYS = 14
RUNWAY_MARKER = "<<RUNWAY_TABLE>>"
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
Do not invent selection criteria, such as price or delivery speed, that the evidence does not state.
Under ## Supply runway, write the line <<RUNWAY_TABLE>> by itself and nothing else. The system replaces it with the inventory table, sorted by days on hand, with urgent items marked.
Items with {urgent_days} or fewer days on hand are urgent. Do not invent any other thresholds or cutoffs.
Outside Supply runway, never restate days on hand or unit counts. Name the products and say they are urgent per the runway table [H].
Each hospital document covers specific products. Apply a document's contract, allocation, or limit only to the products it names, and cite that document.
Substitution and conservation rules come only from hospital documents; cite them with [P1], [P2], ...
Never recommend changes to dosing or prescribing; those are prescriber decisions, not supply actions.
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
    revision_of: int
    previous_draft: str
    review_note: str


def normalize(value):
    value = re.sub(r"(?<=\d),(?=\d)", "", value.lower())
    return re.sub(r"(?<=\d)[ \u00a0\u2009\u202f](?=\d{3}(?!\d))", "", value)


def is_urgent(row):
    return row["days_on_hand"] is not None and float(row["days_on_hand"]) <= URGENT_DAYS


def sorted_inventory(inventory):
    """Lowest days on hand first, unknown days last."""
    return sorted(inventory, key=lambda r: (r["days_on_hand"] is None,
                                            float(r["days_on_hand"] or 0), r["drug_name"]))


def runway_table(inventory):
    """Markdown table of every inventory item, sorted, with urgent items marked."""
    lines = ["| Product | On hand (units) | Days on hand | Urgent |", "|---|---:|---:|:---:|"]
    for r in sorted_inventory(inventory):
        days = "n/a" if r["days_on_hand"] is None else r["days_on_hand"]
        name = str(r["drug_name"]).replace("|", "\\|")
        lines.append(f"| {name} | {r['on_hand_units']} | {days} | {'yes' if is_urgent(r) else ''} |")
    return "\n".join(lines)


def runway_block(inventory):
    """The table plus a code-written line naming the lowest runway, so the model never has to."""
    table = runway_table(inventory)
    rows = sorted_inventory(inventory)
    if not rows or rows[0]["days_on_hand"] is None:
        return table
    lowest = rows[0]
    return f"{table}\n\nLowest runway: {lowest['drug_name']} at {lowest['days_on_hand']} days on hand [H]."


def insert_runway(draft, block):
    return draft.replace(f"`{RUNWAY_MARKER}`", RUNWAY_MARKER).replace(RUNWAY_MARKER, f"\n{block}\n", 1)


def check_draft(draft, evidence):
    evidence_text = normalize(json.dumps(evidence, default=str))
    clean_draft = normalize(draft)
    problems = [f"missing section '{s}'" for s in REQUIRED_SECTIONS if s not in draft]

    for number in set(re.findall(r"(?<![\w.])\d(?:[\d,]*\d)?(?:\.\d+)?(?![\w])", clean_draft)):
        clean = normalize(number)
        if len(clean) < 2 and "." not in clean:
            continue
        if not re.search(rf"(?<![\w.]){re.escape(clean)}(?![\w])", evidence_text):
            problems.append(f"number {number} does not appear in the evidence")

    for row in evidence.get("inventory", []):
        units = str(row["on_hand_units"])
        if is_urgent(row) and not re.search(rf"(?<![\w.]){re.escape(units)}(?![\w])", clean_draft):
            problems.append(f"urgent item missing: {row['drug_name']} has only {row['days_on_hand']} days on hand")

    runway = draft.split("## Supply runway", 1)[-1].split("## Protocol", 1)[0]
    table = runway_table(evidence.get("inventory", []))
    table_lines = sum(line.strip().startswith("|") for line in runway.splitlines())
    if table not in runway or table_lines != len(table.splitlines()):
        problems.append(f"the Supply runway section must contain the line {RUNWAY_MARKER} exactly once "
                        "and no inventory table of your own")
    if RUNWAY_MARKER in draft:
        problems.append(f"write the line {RUNWAY_MARKER} only once, under Supply runway")

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
        revision = None
        if state.get("revision_of"):
            revision = get_action(conn, state["revision_of"])
            if not revision or revision["status"] != "rejected":
                raise ValueError("Only a rejected action from your hospital can be revised.")
        drugs = [dict(r) for r in conn.execute(text(DRUGS_SQL), {"ingredient": state["ingredient"].lower()}).mappings()]
        rxcuis = [d["drug_rxcui"] for d in drugs]
        inventory = [dict(r) for r in conn.execute(text(INVENTORY_SQL), {"rxcuis": rxcuis}).mappings()] if rxcuis else []
        documents = query_private(conn, f"{state['ingredient']} shortage protocol", k=6, rxcuis=rxcuis)
    if not inventory:
        raise ValueError(f"{identity['tenant_name']} does not stock any {state['ingredient']} products in shortage.")
    evidence = {
        "risk": [d for d in drugs if d["drug_rxcui"] in {row["drug_rxcui"] for row in inventory}],
        "inventory": inventory,
        "documents": [{"id": f"P{i}", "title": d["title"], "content": d["content"]}
                      for i, d in enumerate(documents, start=1)],
        "urgent_days": URGENT_DAYS,
    }
    return {"identity": dict(identity), "evidence": evidence, "attempts": 0, "tokens": 0,
            "previous_draft": revision["draft"] if revision else None,
            "review_note": revision["review_note"] if revision else None}


def draft(state):
    block = runway_block(state["evidence"]["inventory"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(**state["identity"], urgent_days=URGENT_DAYS)},
        {"role": "user", "content": f"Drug: {state['ingredient']}\n\nEvidence:\n"
                                    f"{json.dumps(state['evidence'], default=str, separators=(',', ':'))}"},
    ]
    if state.get("problems"):
        messages += [
            {"role": "assistant", "content": state["draft"].replace(block, RUNWAY_MARKER)},
            {"role": "user", "content": "Fix these problems and return the full corrected memo:\n- "
                                        + "\n- ".join(state["problems"])},
        ]
    elif state.get("review_note") and state["attempts"] == 0:
        messages += [
            {"role": "assistant", "content": state["previous_draft"].replace(block, RUNWAY_MARKER)},
            {"role": "user", "content": f"A reviewer rejected this draft with this note:\n{state['review_note']}\n"
                                        "Write a corrected full memo that addresses the note."},
        ]
    content, usage = complete(ANSWER_MODEL, messages)
    return {"draft": insert_runway(content, block), "attempts": state["attempts"] + 1,
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
               "documents": [d["title"] for d in evidence["documents"]], "attempts": state["attempts"],
               "revision_of": state.get("revision_of")}
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


def draft_memo(user_id, ingredient, revision_of=None):
    return build_agent().invoke({"user_id": user_id, "ingredient": ingredient, "revision_of": revision_of})


def main():
    args = sys.argv
    user_id, ingredient = args[1], args[2]
    revision_of = int(args[args.index("--revise") + 1]) if "--revise" in args else None
    try:
        state = draft_memo(user_id, ingredient, revision_of)
    except (PermissionError, ValueError) as err:
        print(err)
        return
    print(state["draft"])
    print(f"\nattempts: {state['attempts']} | tokens: {state['tokens']} | problems: {state.get('problems') or 'none'}")
    if state.get("action_id"):
        print(f"Saved as action {state['action_id']}, pending approval"
              + (f" (revision of {revision_of})" if revision_of else ""))
    else:
        print("Not saved: the draft failed validation after the retry")


if __name__ == "__main__":
    main()
