"""Explore the latest bronze shortage snapshot to design the silver schema."""
import json
from collections import Counter
from pathlib import Path

RAW_DIR = Path("data/raw/shortages")


def load_latest():
    latest = sorted(RAW_DIR.glob("shortages_*.json"))[-1]
    print(f"Reading {latest}\n")
    return json.loads(latest.read_text())


def main():
    records = load_latest()

    openfda_keys = Counter(k for r in records for k in r.get("openfda", {}).keys())
    print("openfda fields (how many records have each):")
    for key, count in openfda_keys.most_common():
        print(f"  {key}: {count}")

    example = next(r for r in records if r.get("openfda"))
    print("\nExample openfda block:")
    print(json.dumps(example["openfda"], indent=2)[:1500])

    print(f"\nDistinct generic names: {len({r.get('generic_name') for r in records})}")
    print(f"Distinct companies: {len({r.get('company_name') for r in records})}")
    print(f"Missing package_ndc: {sum(1 for r in records if not r.get('package_ndc'))}")

    print("\nTop shortage reasons:")
    for reason, count in Counter(r.get("shortage_reason") for r in records).most_common(8):
        print(f"  {count:>4}  {reason}")

    print("\nUpdate types:", dict(Counter(r.get("update_type") for r in records)))

    print("\nSample availability values:")
    for value in list({r.get("availability") for r in records if r.get("availability")})[:5]:
        print(f"  {value[:120]}")


if __name__ == "__main__":
    main()