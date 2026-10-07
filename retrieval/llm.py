"""Single gateway for every LLM call: consistent settings, truncation detection, retry, logging, tracing."""
import os
import sys
import time
from functools import lru_cache

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import text

from observability.tracing import current_ids, span
from tenancy.db import get_app_engine

load_dotenv(".env")


class EmptyCompletion(Exception):
    pass


@lru_cache(maxsize=1)
def client():
    return Groq(api_key=os.environ["GROQ_API_KEY"])


@lru_cache(maxsize=1)
def _engine():
    return get_app_engine()


def log_call(caller, model, usage, latency_ms, finish_reason, attempts, succeeded):
    trace_id, span_id = current_ids()
    try:
        with _engine().begin() as conn:
            conn.execute(text("""
                insert into ops.llm_calls
                    (caller, model, prompt_tokens, completion_tokens, latency_ms, finish_reason,
                     attempts, succeeded, trace_id, span_id)
                values (:caller, :model, :p, :c, :ms, :finish, :attempts, :ok, :trace_id, :span_id)"""),
                {"caller": caller, "model": model, "p": usage["prompt_tokens"], "c": usage["completion_tokens"],
                 "ms": latency_ms, "finish": finish_reason, "attempts": attempts, "ok": succeeded,
                 "trace_id": trace_id, "span_id": span_id})
    except Exception as err:
        print(f"warning: could not log LLM call: {type(err).__name__}")


def complete(model, messages, max_completion_tokens=4096, reasoning_effort="medium", **kwargs):
    caller = sys._getframe(1).f_globals.get("__name__", "unknown")
    with span("llm", model=model, caller=caller) as current:
        start = time.perf_counter()
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        attempts = 0
        for effort in (reasoning_effort, "low"):
            attempts += 1
            response = client().chat.completions.create(
                model=model, messages=messages, temperature=0,
                max_completion_tokens=max_completion_tokens, reasoning_effort=effort, **kwargs)
            usage["prompt_tokens"] += response.usage.prompt_tokens
            usage["completion_tokens"] += response.usage.completion_tokens
            choice = response.choices[0]
            content = (choice.message.content or "").strip()
            current.attributes.update(usage, attempts=attempts, finish_reason=choice.finish_reason)
            if content and choice.finish_reason != "length":
                log_call(caller, model, usage, round((time.perf_counter() - start) * 1000),
                         choice.finish_reason, attempts, True)
                return content, usage
        log_call(caller, model, usage, round((time.perf_counter() - start) * 1000),
                 choice.finish_reason, attempts, False)
        raise EmptyCompletion(f"{model} returned no complete answer (finish_reason={choice.finish_reason})")