"""Single gateway for every LLM call: consistent settings, truncation detection, and one retry."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from groq import Groq

load_dotenv(".env")


class EmptyCompletion(Exception):
    pass


@lru_cache(maxsize=1)
def client():
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def complete(model, messages, max_completion_tokens=4096, reasoning_effort="medium", **kwargs):
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for effort in (reasoning_effort, "low"):
        response = client().chat.completions.create(
            model=model, messages=messages, temperature=0,
            max_completion_tokens=max_completion_tokens, reasoning_effort=effort, **kwargs)
        usage["prompt_tokens"] += response.usage.prompt_tokens
        usage["completion_tokens"] += response.usage.completion_tokens
        choice = response.choices[0]
        content = (choice.message.content or "").strip()
        if content and choice.finish_reason != "length":
            return content, usage
    raise EmptyCompletion(f"{model} returned no complete answer (finish_reason={choice.finish_reason})")