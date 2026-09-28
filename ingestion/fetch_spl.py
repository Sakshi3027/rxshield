"""Download the full SPL label XML from DailyMed for every label linked to a shortage (bronze layer)."""
import time
from pathlib import Path

import pandas as pd
import requests

SPL_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{set_id}.xml"
RAW_DIR = Path("data/raw/spl")
PAUSE_SECONDS = 0.25


def target_set_ids():
    products = pd.read_parquet("data/silver/shortage_products.parquet")
    return sorted(products["spl_set_id"].dropna().unique())


def download(set_id):
    path = RAW_DIR / f"{set_id}.xml"
    if path.exists():
        return "cached"
    response = requests.get(SPL_URL.format(set_id=set_id), timeout=60)
    if response.status_code == 404:
        return "missing"
    response.raise_for_status()
    path.write_bytes(response.content)
    time.sleep(PAUSE_SECONDS)
    return "downloaded"


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    set_ids = target_set_ids()
    print(f"{len(set_ids)} labels to fetch")

    results = {"downloaded": 0, "cached": 0, "missing": 0}
    missing = []
    for i, set_id in enumerate(set_ids, start=1):
        outcome = download(set_id)
        results[outcome] += 1
        if outcome == "missing":
            missing.append(set_id)
        if i % 50 == 0:
            print(f"  {i}/{len(set_ids)} {results}")

    print(f"\nDone: {results}")
    if missing:
        print(f"Missing set IDs (first 10): {missing[:10]}")


if __name__ == "__main__":
    main()