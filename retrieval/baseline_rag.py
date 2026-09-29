"""Baseline RAG: vector search over FDA label chunks, then an LLM answer with citations."""
import os
import sys
import time

from dotenv import load_dotenv
from groq import Groq

from retrieval.vector_search import search

load_dotenv(".env")

MODEL = "openai/gpt-oss-20b"
SYSTEM_PROMPT = """You are a drug shortage assistant for hospital pharmacists.
Answer using ONLY the numbered FDA label excerpts provided.
Cite every claim with its source number, like [1] or [2][3].
If the excerpts do not contain the answer, say exactly what information is missing instead of guessing.
Be concise and clinically precise."""


def build_context(chunks):
    return "\n\n".join(
        f"[{i}] {c['product_label']} | {c['section_name']}\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    )


def answer(question, k=6):
    start = time.perf_counter()
    chunks = search(question, k)
    retrieval_ms = (time.perf_counter() - start) * 1000

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nSources:\n{build_context(chunks)}"},
        ],
    )
    return {
        "question": question,
        "answer": response.choices[0].message.content,
        "sources": chunks,
        "model": MODEL,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "retrieval_ms": round(retrieval_ms),
        "total_ms": round((time.perf_counter() - start) * 1000),
    }


def main():
    question = " ".join(sys.argv[1:]) or "What are the contraindications for bupivacaine?"
    result = answer(question)
    print(f"Q: {result['question']}\n")
    print(result["answer"])
    print("\nSources:")
    for i, chunk in enumerate(result["sources"], start=1):
        print(f"  [{i}] {chunk['similarity']:.3f}  {chunk['product_label']} | {chunk['section_name']}")
    print(f"\n{result['model']} | {result['prompt_tokens']} in / {result['completion_tokens']} out tokens"
          f" | retrieval {result['retrieval_ms']} ms | total {result['total_ms']} ms")


if __name__ == "__main__":
    main()