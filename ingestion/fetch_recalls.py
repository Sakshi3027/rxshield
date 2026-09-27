"""Fetch drug recall enforcement reports from openFDA into the bronze layer."""
from collections import Counter

from ingestion.openfda import fetch_endpoint, save_snapshot


def summarize(records):
    print("\nClassification counts:")
    for value, count in Counter(r.get("classification") for r in records).most_common():
        print(f"  {value}: {count}")

    print("\nStatus counts:")
    for value, count in Counter(r.get("status") for r in records).most_common():
        print(f"  {value}: {count}")

    with_openfda = sum(1 for r in records if r.get("openfda"))
    print(f"\nRecords with openfda block: {with_openfda} of {len(records)}")

    dates = sorted(r["recall_initiation_date"] for r in records if r.get("recall_initiation_date"))
    print(f"Recall initiation range: {dates[0]} to {dates[-1]}")

    all_fields = sorted(set().union(*(r.keys() for r in records)))
    print(f"\nAll fields seen: {all_fields}")


if __name__ == "__main__":
    records = fetch_endpoint("drug/enforcement")
    save_snapshot(records, "recalls")
    summarize(records)