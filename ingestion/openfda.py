"""Shared helpers for pulling full datasets from openFDA endpoints into the bronze layer."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.fda.gov"
PAGE_SIZE = 1000
MAX_RECORDS = 26000


def fetch_endpoint(endpoint, search=None):
    records = []
    skip = 0
    while True:
        params = {"limit": PAGE_SIZE, "skip": skip}
        if search:
            params["search"] = search
        response = requests.get(f"{BASE_URL}/{endpoint}.json", params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        total = payload["meta"]["results"]["total"]
        if total > MAX_RECORDS:
            raise ValueError(f"{endpoint} has {total} records, above openFDA's paging limit. Narrow it with a search filter.")
        records.extend(payload["results"])
        print(f"  {endpoint}: fetched {len(records)} of {total}")
        skip += PAGE_SIZE
        if skip >= total:
            break
    return records


def save_snapshot(records, name):
    raw_dir = Path("data/raw") / name
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = raw_dir / f"{name}_{stamp}.json"
    path.write_text(json.dumps(records, indent=2))
    print(f"  saved {len(records)} records to {path}")
    return path