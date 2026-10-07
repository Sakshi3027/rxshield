"""LLM-as-judge for answer faithfulness, calibrated against planted errors."""
import json
import re
import sys
import time
from collections import deque
from pathlib import Path

import pandas as pd

from retrieval.llm import capture_calls, complete
from retrieval.router import answer_routed

JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_TPM = 7000
PLANTED_CLAIM = "It is also manufactured at a facility in Nuuk, Greenland [G]."
PLANTED_MARKER = "Greenland"
DECOY_NUMBERS = ["97", "83", "61", "47", "389"]
NUMBER = re.compile(r"(?<![\[\w.])\d+(?:\.\d+)?(?![\]\w])")
RESULTS = Path("evals/results/judge_calibration.json")

JUDGE_PROMPT = """You are a strict evaluator of a drug shortage assistant.
You receive the SOURCE MATERIAL the assistant was given and the ANSWER it wrote.
Split the answer into atomic factual claims. For each claim, decide whether the source material directly supports it.
A claim is supported only if the source states it. Plausible general knowledge does not count.
Numbers, names, places and dates must match the source exactly.
Citation markers such as [1], [G], [L2], [H], [P1] are not claims.
Return only JSON: {"claims": [{"claim": "...", "supported": true, "reason": "..."}], "answers_question": true}"""


class TokenBudget:
    """Sliding one-minute window of tokens spent on one model, to stay under the provider's rate limit."""

    def __init__(self, per_minute):
        self.per_minute = per_minute
        self.events = deque()

    def record(self, tokens):
        self.events.append((time.monotonic(), tokens))

    def wait(self, needed):
        while True:
            now = time.monotonic()
            while self.events and now - self.events[0][0] > 60:
                self.events.popleft()
            used = sum(tokens for _, tokens in self.events)
            if not self.events or used + needed <= self.per_minute:
                return
            time.sleep(60 - (now - self.events[0][0]) + 0.5)


def parse_json(content):
    cleaned = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(cleaned)


def judge(source, answer, budget):
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"SOURCE MATERIAL:\n{source}\n\nANSWER:\n{answer}"},
    ]
    budget.wait(len(source + answer) // 4 + 1500)
    content, usage = complete(JUDGE_MODEL, messages, max_completion_tokens=3000,
                              response_format={"type": "json_object"})
    budget.record(usage["prompt_tokens"] + usage["completion_tokens"])
    verdict = parse_json(content)
    claims = verdict.get("claims", [])
    unsupported = [c.get("claim", "") for c in claims if not c.get("supported")]
    return {
        "claims": len(claims),
        "unsupported": unsupported,
        "faithfulness": round(1 - len(unsupported) / len(claims), 3) if claims else None,
        "answers_question": bool(verdict.get("answers_question")),
    }


def plant_number(answer, source):
    match = NUMBER.search(answer)
    decoy = next((d for d in DECOY_NUMBERS if d not in source), None)
    if not match or decoy is None:
        return None, None
    return answer[:match.start()] + decoy + answer[match.end():], decoy


def evaluate(question, budget):
    budget.wait(2500)
    with capture_calls() as calls:
        result = answer_routed(question)
    for call in calls:
        if call["model"] == JUDGE_MODEL:
            budget.record(call["tokens"])
    source = calls[-1]["messages"][-1]["content"]
    answer = result["answer"]

    variants = [("original", answer, None)]
    swapped, decoy = plant_number(answer, source)
    if swapped:
        variants.append(("number_swap", swapped, decoy))
    if PLANTED_MARKER not in source:
        variants.append(("planted_claim", f"{answer.rstrip()} {PLANTED_CLAIM}", PLANTED_MARKER))

    rows = []
    for variant, text_value, marker in variants:
        scored = judge(source, text_value, budget)
        caught = None if marker is None else any(marker in claim for claim in scored["unsupported"])
        rows.append({"question": question, "route": result["route"], "variant": variant,
                     "caught": caught, **scored})
        print(f"  {variant:<14} faithfulness={scored['faithfulness']}  caught={caught}")
    return rows


def summarize(rows):
    df = pd.DataFrame(rows)
    originals = df[df["variant"] == "original"]
    planted = df[df["variant"] != "original"]
    grounded = (originals["unsupported"].str.len() == 0).mean()
    print(f"\nOriginal answers: mean faithfulness {originals['faithfulness'].mean():.3f}, "
          f"fully grounded {grounded:.0%}")
    print(f"Planted errors caught: {int(planted['caught'].astype(bool).sum())}/{len(planted)}")
    print(planted.groupby("variant")["caught"].apply(lambda s: s.astype(bool).mean()).to_string())
    for _, row in originals[originals["unsupported"].str.len() > 0].iterrows():
        print(f"\nFlagged original: {row['question']}\n  unsupported: {row['unsupported']}")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    questions = [q["question"] for q in json.loads(Path("evals/questions.json").read_text())][:limit]
    budget = TokenBudget(JUDGE_TPM)
    rows = []
    for i, question in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {question}")
        rows.extend(evaluate(question, budget))
    RESULTS.write_text(json.dumps(rows, indent=2))
    summarize(rows)


if __name__ == "__main__":
    main()