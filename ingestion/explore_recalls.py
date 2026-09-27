"""Explore recall data to measure how recalls can be linked to shortage products."""
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

NDC_PATTERN = re.compile(r"\b\d{4,5}-\d{3,4}-\d{1,2}\b")
REASON_KEYWORDS = [
    "cgmp", "sterility", "contamina", "particulate", "subpotent",
    "superpotent", "impurit", "dissolution", "label", "nitrosamine",
]


def load_latest(name):
    latest = sorted(Path("data/raw", name).glob(f"{name}_*.json"))[-1]
    return json.loads(latest.read_text())


def extract_ndcs(recall):
    fields = ["product_description", "code_info", "more_code_info"]
    text = " ".join(recall.get(f) or "" for f in fields)
    return set(NDC_PATTERN.findall(text))


def to_product_ndc(package_ndc):
    return "-".join(package_ndc.split("-")[:2])


def main():
    recalls = load_latest("recalls")
    events = pd.read_parquet("data/silver/shortage_events.parquet")
    shortage_products = set(events["product_ndc"])

    text_hits = 0
    recall_products = []
    for r in recalls:
        text_ndcs = extract_ndcs(r)
        if text_ndcs:
            text_hits += 1
        openfda_products = set(r.get("openfda", {}).get("product_ndc", []))
        recall_products.append({to_product_ndc(n) for n in text_ndcs} | openfda_products)

    linkable = sum(1 for p in recall_products if p)
    matched = [p & shortage_products for p in recall_products]
    recalls_touching_shortages = sum(1 for m in matched if m)
    shortage_products_recalled = set().union(*matched)

    print("Linking coverage:")
    print(f"  recalls with an NDC in their text: {text_hits} of {len(recalls)}")
    print(f"  recalls linkable by text or openfda: {linkable} of {len(recalls)}")
    print(f"  recalls that touch a shortage product: {recalls_touching_shortages}")
    print(f"  shortage products with at least one recall: {len(shortage_products_recalled)} of {len(shortage_products)}")

    print("\nRecalls and openfda coverage by year (last 10 years):")
    by_year = Counter(r["recall_initiation_date"][:4] for r in recalls)
    openfda_by_year = Counter(r["recall_initiation_date"][:4] for r in recalls if r.get("openfda"))
    for year in sorted(by_year)[-10:]:
        print(f"  {year}: {by_year[year]:>5} recalls, {openfda_by_year[year]:>4} with openfda")

    print("\nReason keywords:")
    reasons = [(r.get("reason_for_recall") or "").lower() for r in recalls]
    for kw in REASON_KEYWORDS:
        print(f"  {kw}: {sum(1 for text in reasons if kw in text)}")

    print("\nTop recalling countries:")
    for country, count in Counter(r.get("country") for r in recalls).most_common(8):
        print(f"  {country}: {count}")


if __name__ == "__main__":
    main()