"""Release gate: benchmark accuracy, deterministic number grounding, and judged faithfulness."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from groq import APIConnectionError, RateLimitError

from evals.benchmark import QUESTIONS, expected_terms, score, validate_gold
from evals.judge import JUDGE_MODEL, JUDGE_TPM, JudgeError, TokenBudget, judge, unverified_numbers
from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from retrieval.llm import capture_calls
from retrieval.router import answer_routed

MIN_PASS_RATE = 0.9
MIN_FAITHFULNESS = 0.95
RESULTS_DIR = Path("evals/results")


def check(question, budget):
    base = {"id": question["id"], "question": question["question"], "unverified_numbers": [],
            "faithfulness": None, "unsupported": [], "judge_error": False}
    budget.wait(2500)
    try:
        with capture_calls() as calls:
            result = answer_routed(question["question"])
    except NotAnswerable:
        return {**base, "passed": False, "missing": ["<not answerable>"], "forbidden_found": []}
    for call in calls:
        if call["model"] == JUDGE_MODEL:
            budget.record(call["tokens"])

    source = calls[-1]["messages"][-1]["content"]
    answer = result["answer"]
    row = {**base, **score(answer, question), "route": result["route"], "answer": answer,
           "unverified_numbers": unverified_numbers(answer, source)}
    try:
        verdict = judge(source, answer, budget)
    except JudgeError:
        return {**row, "judge_error": True}
    return {**row, "faithfulness": verdict["faithfulness"], "unsupported": verdict["unsupported"]}


def decide(rows):
    df = pd.DataFrame(rows)
    pass_rate = df["passed"].mean()
    ungrounded = int((df["unverified_numbers"].str.len() > 0).sum())
    judged = df["faithfulness"].dropna()
    faithfulness = judged.mean() if len(judged) else None
    judge_errors = int(df["judge_error"].sum())
    return [
        ("Benchmark pass rate", f"{pass_rate:.0%}", f">= {MIN_PASS_RATE:.0%}", pass_rate >= MIN_PASS_RATE),
        ("Answers with ungrounded numbers", str(ungrounded), "0", ungrounded == 0),
        ("Mean judged faithfulness", "n/a" if faithfulness is None else f"{faithfulness:.3f}",
         f">= {MIN_FAITHFULNESS}", faithfulness is not None and faithfulness >= MIN_FAITHFULNESS),
        ("Judge errors", str(judge_errors), "0", judge_errors == 0),
    ]


def render(checks, rows):
    lines = ["## RxShield eval gate", "", "| Check | Value | Required | Result |", "|---|---|---|---|"]
    lines += [f"| {name} | {value} | {required} | {'pass' if ok else 'FAIL'} |"
              for name, value, required, ok in checks]
    details = []
    for r in rows:
        if not r["passed"]:
            details.append(f"- {r['id']} benchmark: missing {r['missing']}, forbidden {r['forbidden_found']}")
        if r["unverified_numbers"]:
            details.append(f"- {r['id']} ungrounded numbers: {r['unverified_numbers']}")
        if r["unsupported"]:
            details.append(f"- {r['id']} unsupported claims: {r['unsupported']}")
        if r["judge_error"]:
            details.append(f"- {r['id']} judge returned malformed output twice")
    if details:
        lines += ["", "### Details", *details]
    return "\n".join(lines) + "\n"


def main():
    questions = json.loads(QUESTIONS.read_text())
    with get_driver() as driver:
        for question in questions:
            question["expected"] = expected_terms(driver, question)
    validate_gold(questions)

    budget = TokenBudget(JUDGE_TPM)
    rows = []
    try:
        for question in questions:
            print(f"{question['id']} {question['question']}")
            rows.append(check(question, budget))
    except (RateLimitError, APIConnectionError) as err:
        print(f"\nGATE INCONCLUSIVE: {type(err).__name__} after {len(rows)}/{len(questions)} questions.")
        sys.exit(2)

    checks = decide(rows)
    report = render(checks, rows)
    print("\n" + report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as summary:
            summary.write(report)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RESULTS_DIR / f"gate_{stamp}.json").write_text(json.dumps(rows, indent=2, default=str))
    sys.exit(0 if all(ok for *_, ok in checks) else 1)


if __name__ == "__main__":
    main()