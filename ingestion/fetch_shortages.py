"""Fetch every drug shortage record from openFDA into the bronze layer."""
from collections import Counter

from ingestion.openfda import fetch_endpoint, save_snapshot


def summarize(records):
    statuses = Counter(r.get("status") for r in records)
    print("\nStatus counts:")
    for status, count in statuses.most_common():
        print(f"  {status}: {count}")

    with_openfda = sum(1 for r in records if r.get("openfda"))
    print(f"\nRecords with openfda block: {with_openfda} of {len(records)}")

    all_fields = sorted(set().union(*(r.keys() for r in records)))
    print(f"\nAll fields seen: {all_fields}")


if __name__ == "__main__":
    records = fetch_endpoint("drug/shortages")
    save_snapshot(records, "shortages")
    summarize(records)