"""Single gateway for every LLM call: consistent settings, truncation detection, retry, logging, tracing."""
import contextvars
import os
import sys
import time
from contextlib import contextmanager
from functools import lru_cache

from dotenv import load_dotenv
from groq import Groq

from observability import writer
from observability.tracing import current_ids, span

load_dotenv(".env")

LOG_SQL = """
    insert into ops.llm_calls
        (caller, model, prompt_tokens, completion_tokens, latency_ms, finish_reason,
         attempts, succeeded, trace_id, span_id)
    values (:caller, :model, :p, :c, :ms, :finish, :attempts, :ok, :trace_id, :span_id)
"""

_capture = contextvars.ContextVar("rxshield_llm_capture", default=None)


class EmptyCompletion(Exception):
    pass


@lru_cache(maxsize=1)
def client():
    return Groq(api_key=os.environ["GROQ_API_KEY"])


@contextmanager
def capture_calls():
    """Collect full prompts and outputs in memory for evaluation. Never persisted."""
    calls = []
    token = _capture.set(calls)
    try:
        yield calls
    finally:
        _capture.reset(token)


def log_call(caller, model, usage, latency_ms, finish_reason, attempts, succeeded):
    trace_id, span_id = current_ids()
    writer.submit(LOG_SQL, {
        "caller": caller, "model": model, "p": usage["prompt_tokens"], "c": usage["completion_tokens"],
        "ms": latency_ms, "finish": finish_reason, "attempts": attempts, "ok": succeeded,
        "trace_id": trace_id, "span_id": span_id})


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
                captured = _capture.get()
                if captured is not None:
                    captured.append({"caller": caller, "model": model, "messages": messages,
                                     "content": content, "tokens": sum(usage.values())})
                return content, usage
        log_call(caller, model, usage, round((time.perf_counter() - start) * 1000),
                 choice.finish_reason, attempts, False)
        raise EmptyCompletion(f"{model} returned no complete answer (finish_reason={choice.finish_reason})")