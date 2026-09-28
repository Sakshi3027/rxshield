"""Map shortage packages to RxNorm concepts and classes via the NLM RxNav API (bronze layer)."""
import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://rxnav.nlm.nih.gov/REST"
RAW_DIR = Path("data/raw/rxnorm")
PAUSE_SECONDS = 0.1


def cached_get(kind, key, url, params):
    path = RAW_DIR / kind / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text)
    time.sleep(PAUSE_SECONDS)
    return response.json()


def ndc_to_rxcui(package_ndc):
    data = cached_get("ndcstatus", package_ndc, f"{BASE_URL}/ndcstatus.json", {"ndc": package_ndc})
    return data.get("ndcStatus", {}).get("rxcui") or None


def related_concepts(rxcui):
    data = cached_get("related", rxcui, f"{BASE_URL}/rxcui/{rxcui}/related.json", {"tty": "IN SCDF"})
    concepts = []
    for group in data.get("relatedGroup", {}).get("conceptGroup", []):
        for concept in group.get("conceptProperties", []):
            concepts.append((concept["tty"], concept["rxcui"]))
    return concepts


def fetch_atc(ingredient_rxcui):
    cached_get(
        "atc", ingredient_rxcui,
        f"{BASE_URL}/rxclass/class/byRxcui.json",
        {"rxcui": ingredient_rxcui, "relaSource": "ATC"},
    )

def equivalents(rxcui):
    data = cached_get("equivalents", rxcui, f"{BASE_URL}/rxcui/{rxcui}/related.json", {"tty": "SCD SBD"})
    return [
        concept["rxcui"]
        for group in data.get("relatedGroup", {}).get("conceptGroup", [])
        for concept in group.get("conceptProperties", [])
    ]


def fetch_ndcs(rxcui):
    cached_get("ndcs", rxcui, f"{BASE_URL}/rxcui/{rxcui}/ndcs.json", {})


def main():
    events = pd.read_parquet("data/silver/shortage_events.parquet")
    packages = sorted(events["package_ndc"].unique())

    print(f"Step 1: mapping {len(packages)} packages to RxCUIs")
    mapped = {}
    for i, ndc in enumerate(packages, start=1):
        mapped[ndc] = ndc_to_rxcui(ndc)
        if i % 200 == 0:
            print(f"  {i}/{len(packages)}")
    drug_rxcuis = sorted({r for r in mapped.values() if r})
    mapped_count = sum(1 for r in mapped.values() if r)
    print(f"  {mapped_count} of {len(packages)} packages mapped to {len(drug_rxcuis)} distinct drugs")

    print(f"\nStep 2: fetching ingredients and dose form groups for {len(drug_rxcuis)} drugs")
    ingredients = set()
    for i, rxcui in enumerate(drug_rxcuis, start=1):
        for tty, related in related_concepts(rxcui):
            if tty == "IN":
                ingredients.add(related)
        if i % 200 == 0:
            print(f"  {i}/{len(drug_rxcuis)}")
    print(f"  found {len(ingredients)} distinct ingredients")

    print(f"\nStep 3: fetching ATC classes for {len(ingredients)} ingredients")
    for ingredient in sorted(ingredients):
        fetch_atc(ingredient)
    print("  done")

    print(f"\nStep 4: fetching generic and brand equivalents for {len(drug_rxcuis)} drugs")
    equivalent_rxcuis = set()
    for i, rxcui in enumerate(drug_rxcuis, start=1):
        equivalent_rxcuis.update(equivalents(rxcui))
        if i % 200 == 0:
            print(f"  {i}/{len(drug_rxcuis)}")
    print(f"  {len(equivalent_rxcuis)} distinct equivalent drugs")

    print(f"\nStep 5: fetching listed NDCs for {len(equivalent_rxcuis)} equivalent drugs")
    for i, rxcui in enumerate(sorted(equivalent_rxcuis), start=1):
        fetch_ndcs(rxcui)
        if i % 200 == 0:
            print(f"  {i}/{len(equivalent_rxcuis)}")
    print("  done")
    

if __name__ == "__main__":
    main()