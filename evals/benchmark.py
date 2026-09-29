"""Benchmark baseline RAG vs GraphRAG on a gold question set with graph-derived ground truth."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from groq import RateLimitError

from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from retrieval import baseline_rag, graph_rag

QUESTIONS = Path("evals/questions.json")
RESULTS_DIR = Path("evals/results")
SYSTEMS = {"baseline": baseline_rag.answer, "graph_rag": graph_rag.answer}

NONE_PHRASES = [
    "no matching", "no critical", "none", "not found", "no drugs",
    "do not contain", "does not contain", "no information",
]

def expected_terms(driver, question):
    terms = [t.lower() for t in question.get("must_include", [])]
    if question.get("truth_cypher"):
        records, _, _ = driver.execute_query(question["truth_cypher"])
        terms += [str(t).lower() for t in records[0]["expected"]]
    return sorted(set(terms))


def call_with_retry(fn, text, attempts=4):
    for attempt in range(1, attempts + 1):
        try:
            return fn(text)
        except RateLimitError:
            if attempt == attempts:
                raise
            wait = 20 * attempt
            print(f"    rate limited, waiting {wait}s")
            time.sleep(wait)


def score(answer_text, question):
    text = answer_text.lower()
    forbidden = [t.lower() for t in question.get("must_not_include", [])]
    leaked = [t for t in forbidden if t in text]

    if question.get("expect_none"):
        said_none = any(phrase in text for phrase in NONE_PHRASES)
        return {"recall": 1.0 if said_none else 0.0,
                "missing": [] if said_none else ["<should say none>"],
                "forbidden_found": leaked, "passed": said_none and not leaked}

    expected = question["expected"]
    missing = [t for t in expected if t not in text]
    recall = (len(expected) - len(missing)) / len(expected)
    return {"recall": round(recall, 3), "missing": missing, "forbidden_found": leaked,
            "passed": not missing and not leaked}


def run_one(system, fn, question):
    row = {"id": question["id"], "category": question["category"], "system": system,
           "question": question["question"], "expected": question["expected"]}
    try:
        out = call_with_retry(fn, question["question"])
    except (NotAnswerable, PermissionError) as err:
        return {**row, "passed": False, "recall": 0.0, "error": str(err)}
    except Exception as err:
        return {**row, "passed": False, "recall": 0.0, "error": f"{type(err).__name__}: {err}"}
    forbidden = [t.lower() for t in question.get("must_not_include", [])]
    return {**row, **score(out["answer"], question),
            "tokens": out["prompt_tokens"] + out["completion_tokens"],
            "total_ms": out["total_ms"], "cypher": out.get("cypher"), "answer": out["answer"]}


def summarize(results):
    df = pd.DataFrame(results)
    print("\nPass rate by category:")
    print(df.pivot_table(index="category", columns="system", values="passed", aggfunc="mean").round(2).to_string())
    print("\nOverall:")
    overall = df.groupby("system").agg(
        pass_rate=("passed", "mean"), avg_recall=("recall", "mean"),
        avg_tokens=("tokens", "mean"), avg_ms=("total_ms", "mean"),
    ).round(2)
    print(overall.to_string())

def validate_gold(questions):
    problems = []
    for q in questions:
        if q.get("expect_none") and q["expected"]:
            problems.append(f"{q['id']} expects no answer, but the graph now returns {q['expected']}")
        if not q.get("expect_none") and not q["expected"]:
            problems.append(f"{q['id']} has an empty expected answer")
    if problems:
        raise ValueError("Gold set problems:\n" + "\n".join(problems))
    
def main():
    questions = json.loads(QUESTIONS.read_text())
    with get_driver() as driver:
        for question in questions:
            question["expected"] = expected_terms(driver, question)

    if "--truth" in sys.argv:
        for q in questions:
            flag = " (expects none)" if q.get("expect_none") else ""
            print(f"{q['id']} [{q['category']}] {q['question']}{flag}\n    expected: {q['expected']}")
        validate_gold(questions)
        print("\nGold set OK")
        return

    validate_gold(questions)

    results = []
    for question in questions:
        print(f"{question['id']} {question['question']}")
        for system, fn in SYSTEMS.items():
            row = run_one(system, fn, question)
            status = "PASS" if row["passed"] else "FAIL"
            detail = row.get("error") or f"missing {row.get('missing')} forbidden {row.get('forbidden_found')}"
            print(f"  {system:10s} {status}  {detail if not row['passed'] else ''}")
            results.append(row)

    summarize(results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"benchmark_{stamp}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nSaved {len(results)} results to {path}")


if __name__ == "__main__":
    main()