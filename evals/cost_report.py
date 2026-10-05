"""Summarize LLM usage by component: volume, tokens, latency, retries, and failures."""
import pandas as pd
from sqlalchemy import text

from ingestion.db import get_engine

REPORT_SQL = """
    select caller, model,
           count(*) as calls,
           round(avg(prompt_tokens)) as avg_prompt,
           round(avg(completion_tokens)) as avg_completion,
           round(percentile_cont(0.5) within group (order by latency_ms)) as p50_ms,
           round(percentile_cont(0.95) within group (order by latency_ms)) as p95_ms,
           round(100.0 * avg((attempts > 1)::int), 1) as retry_pct,
           sum((not succeeded)::int) as failures
    from ops.llm_calls
    group by caller, model
    order by sum(prompt_tokens + completion_tokens) desc
"""


def main():
    report = pd.read_sql(text(REPORT_SQL), get_engine())
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()