"""Print a request trace as an indented tree. Operator tool: uses the admin connection."""
import sys

import pandas as pd
from sqlalchemy import text

from ingestion.db import get_engine

LATEST_SQL = text("""
    select trace_id from ops.spans
    where parent_id is null and name = 'request'
    order by started_at desc limit 1""")
SPANS_SQL = text("select * from ops.spans where trace_id = :t order by started_at")


def print_tree(spans, parent_id=None, depth=0):
    if parent_id is None:
        children = spans[spans["parent_id"].isna()]
    else:
        children = spans[spans["parent_id"] == parent_id]
    for _, row in children.iterrows():
        flag = "" if row["status"] == "ok" else f"  [{row['status']}: {row['error_type']}]"
        print(f"{'    ' * depth}{row['name']}  {float(row['duration_ms']):.0f} ms  {row['attributes']}{flag}")
        print_tree(spans, row["span_id"], depth + 1)


def main():
    with get_engine().connect() as conn:
        trace_id = sys.argv[1] if len(sys.argv) > 1 else conn.execute(LATEST_SQL).scalar()
        if trace_id is None:
            print("No request traces yet.")
            return
        spans = pd.read_sql(SPANS_SQL, conn, params={"t": trace_id})
    print(f"trace {trace_id}\n")
    print_tree(spans)


if __name__ == "__main__":
    main()