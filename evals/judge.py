"""LLM-as-judge for answer faithfulness, calibrated against blatant and subtle planted errors."""
import argparse
import json
import re
import time
from collections import deque
from pathlib import Path
from groq import RateLimitError

import pandas as pd

from retrieval.llm import capture_calls, complete
from retrieval.router import answer_routed

JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_TPM = 7000
PLANTED_CLAIM = "It is also manufactured at a facility in Nuuk, Greenland [G]."
PLANTED_MARKER = "Greenland"
PLAUSIBLE_COUNTRIES = ["India", "China", "Germany", "Italy"]
DECOY_NUMBERS = ["97", "83", "61", "47", "389"]
NUMBER_VARIANTS = {"number_swap", "number_shift"}
NUMBER = re.compile(r"(?<![\[\w.])\d+(?:\.\d+)?(?![\]\w])")
RESULTS = Path("evals/results/judge_calibration.json")

JUDGE_PROMPT = """You are a strict evaluator of a drug shortage assistant.
You receive the SOURCE MATERIAL the assistant was given and the ANSWER it wrote.
Split the answer into atomic factual claims. For each claim, decide whether the source material directly supports it.
A claim is supported only if the source states it. Plausible general knowledge does not count.
Numbers, names, places and dates must match the source exactly.
Citation markers such as [1], [G], [L2], [H], [P1] are not claims.
Statements about the evidence itself, such as noting that some information is not in the sources, are not claims.
Return only JSON: {"claims": [{"claim": "...", "supported": true, "reason": "..."}], "answers_question": true}"""
SHAPE_FIX = ("Each item in claims must be an object with a string 'claim', a boolean 'supported' "
             "and a string 'reason'. Return the corrected JSON only.")


class JudgeError(Exception):
    pass


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


def valid_verdict(verdict):
    claims = verdict.get("claims") if isinstance(verdict, dict) else None
    return isinstance(claims, list) and all(
        isinstance(c, dict) and isinstance(c.get("claim"), str) and isinstance(c.get("supported"), bool)
        for c in claims)


def appears(number, text_value):
    return re.search(rf"(?<![\d.]){re.escape(number)}(?![\d.])", text_value) is not None


def unverified_numbers(answer, source):
    return sorted({m.group() for m in NUMBER.finditer(answer) if not appears(m.group(), source)})


def replace_first_number(answer, source, candidates_for):
    match = NUMBER.search(answer)
    if not match:
        return None, None
    decoy = next((c for c in candidates_for(match.group()) if not appears(c, source)), None)
    if decoy is None:
        return None, None
    return answer[:match.start()] + decoy + answer[match.end():], decoy


def plant_number(answer, source):
    return replace_first_number(answer, source, lambda value: DECOY_NUMBERS)


def shift_number(answer, source):
    def nearby(value):
        base = float(value)
        shifted = [base + d for d in (1, -1, 2, -2) if base + d >= 0]
        return [f"{v:g}" if "." in value else str(int(v)) for v in shifted]

    return replace_first_number(answer, source, nearby)


def contains_marker(marker, text_value):
    return appears(marker, text_value) if marker[0].isdigit() else marker in text_value


def judge(source, answer, budget):
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"SOURCE MATERIAL:\n{source}\n\nANSWER:\n{answer}"},
    ]
    for attempt in range(2):
        budget.wait(len(source + answer) // 4 + 1500)
        content, usage = complete(JUDGE_MODEL, messages, max_completion_tokens=3000,
                                  response_format={"type": "json_object"})
        budget.record(usage["prompt_tokens"] + usage["completion_tokens"])
        try:
            verdict = parse_json(content)
        except json.JSONDecodeError:
            verdict = None
        if valid_verdict(verdict):
            break
        messages = messages + [{"role": "assistant", "content": content},
                               {"role": "user", "content": SHAPE_FIX}]
    else:
        raise JudgeError("judge returned malformed output twice")

    claims = verdict["claims"]
    unsupported = [c["claim"] for c in claims if not c["supported"]]
    return {
        "claims": len(claims),
        "unsupported": unsupported,
        "faithfulness": round(1 - len(unsupported) / len(claims), 3) if claims else None,
        "answers_question": bool(verdict.get("answers_question")),
    }


def build_variants(answer, source):
    variants = [("original", answer, None)]
    for kind, (changed, marker) in {"number_swap": plant_number(answer, source),
                                    "number_shift": shift_number(answer, source)}.items():
        if changed:
            variants.append((kind, changed, marker))
    if PLANTED_MARKER not in source:
        variants.append(("planted_claim", f"{answer.rstrip()} {PLANTED_CLAIM}", PLANTED_MARKER))
    country = next((c for c in PLAUSIBLE_COUNTRIES if c not in source), None)
    if country:
        variants.append(("plausible_claim",
                         f"{answer.rstrip()} Some of these products are also manufactured in {country} [G].",
                         country))
    return variants


def evaluate(question, budget):
    budget.wait(2500)
    with capture_calls() as calls:
        result = answer_routed(question)
    for call in calls:
        if call["model"] == JUDGE_MODEL:
            budget.record(call["tokens"])
    source = calls[-1]["messages"][-1]["content"]

    rows = []
    for variant, text_value, marker in build_variants(result["answer"], source):
        numbers = unverified_numbers(text_value, source)
        base = {"question": question, "route": result["route"], "variant": variant, "marker": marker,
                "answer": text_value, "unverified_numbers": numbers,
                "numbers_caught": marker in numbers if variant in NUMBER_VARIANTS else None}
        try:
            scored = judge(source, text_value, budget)
        except JudgeError:
            rows.append({**base, "judge_error": True})
            print(f"  {variant:<16} judge_error")
            continue
        caught = None if marker is None else any(contains_marker(marker, c) for c in scored["unsupported"])
        rows.append({**base, "judge_error": False, "caught": caught, **scored})
        print(f"  {variant:<16} faithfulness={scored['faithfulness']}  caught={caught}  "
              f"unverified_numbers={numbers}")
    return rows


def summarize(rows):
    df = pd.DataFrame(rows)
    errors = int(df["judge_error"].sum())
    df = df[~df["judge_error"]]
    originals = df[df["variant"] == "original"]
    planted = df[df["variant"] != "original"]

    grounded = (originals["unsupported"].str.len() == 0).mean()
    print(f"\nOriginal answers: mean faithfulness {originals['faithfulness'].mean():.3f}, "
          f"fully grounded {grounded:.0%}")
    print(f"Planted errors caught by judge: {int(planted['caught'].astype(bool).sum())}/{len(planted)}")
    print(planted.groupby("variant")["caught"].agg(
        caught=lambda s: int(s.astype(bool).sum()), total="size").to_string())

    numeric = planted[planted["variant"].isin(NUMBER_VARIANTS)]
    if len(numeric):
        judge_hits = numeric["caught"].astype(bool)
        check_hits = numeric["numbers_caught"].astype(bool)
        print(f"\nNumber errors of {len(numeric)}: judge {int(judge_hits.sum())}, "
              f"number check {int(check_hits.sum())}, either {int((judge_hits | check_hits).sum())}")
    noisy = originals[originals["unverified_numbers"].str.len() > 0]
    print(f"Original answers with numbers not in the source: {len(noisy)}/{len(originals)}")
    for _, row in noisy.iterrows():
        print(f"  {row['question']}: {row['unverified_numbers']}")

    for _, row in planted[~planted["caught"].astype(bool)].iterrows():
        sentence = next((s for s in re.split(r"(?<=[.!?])\s+|\n", row["answer"])
                         if contains_marker(row["marker"], s)), "")
        print(f"\nJudge missed {row['variant']} ({row['marker']}): {row['question']}\n  planted in: {sentence.strip()}")
    if errors:
        print(f"\nJudge errors (malformed output twice): {errors}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    questions = [q["question"] for q in json.loads(Path("evals/questions.json").read_text())][:args.limit]
    rows = json.loads(RESULTS.read_text()) if args.resume and RESULTS.exists() else []
    done = {row["question"] for row in rows}
    budget = TokenBudget(JUDGE_TPM)
    for i, question in enumerate(questions, start=1):
        if question in done:
            print(f"[{i}/{len(questions)}] already judged, skipping")
            continue
        print(f"[{i}/{len(questions)}] {question}")
        try:
            rows.extend(evaluate(question, budget))
        except RateLimitError:
            print("\nProvider token limit reached. Finished questions are saved; "
                  "rerun with --resume after the limit resets.")
            break
        RESULTS.write_text(json.dumps(rows, indent=2))
    summarize(rows)


if __name__ == "__main__":
    main()