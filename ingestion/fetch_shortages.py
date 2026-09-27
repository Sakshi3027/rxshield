"""Fetch every drug shortage record from openFDA and save the raw JSON (bronze layer)."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.fda.gov/drug/shortages.json"
PAGE_SIZE = 1000
RAW_DIR = Path("data/raw/shortages")


def fetch_all():
    records = []
    skip = 0
    while True:
        params = {"limit": PAGE_SIZE, "skip": skip}
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        records.extend(payload["results"])
        total = payload["meta"]["results"]["total"]
        print(f"Fetched {len(records)} of {total}")
        skip += PAGE_SIZE
        if skip >= total:
            break
    return records


def save(records):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"shortages_{stamp}.json"
    path.write_text(json.dumps(records, indent=2))
    return path


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
    records = fetch_all()
    path = save(records)
    print(f"\nSaved to {path}")
    summarize(records)