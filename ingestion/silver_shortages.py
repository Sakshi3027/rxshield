"""Transform the latest bronze shortage snapshot into clean silver tables."""
import hashlib
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/shortages")
SILVER_DIR = Path("data/silver")

AVAILABILITY_FIXES = {
    "unavailable": "Unavailable",
    "unvailable": "Unavailable",
    "limited availability": "Limited Availability",
    "available": "Available",
}

DATE_COLUMNS = ["initial_posting_date", "update_date", "change_date", "discontinued_date"]


def load_latest():
    latest = sorted(RAW_DIR.glob("shortages_*.json"))[-1]
    snapshot_ts = latest.stem.replace("shortages_", "")
    return json.loads(latest.read_text()), snapshot_ts


def make_shortage_id(record):
    key = "|".join([
        record.get("package_ndc", ""),
        record.get("company_name", ""),
        record.get("initial_posting_date", ""),
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def first(values):
    return values[0] if values else None


def normalize_availability(value):
    if not value:
        return None
    return AVAILABILITY_FIXES.get(value.strip().lower(), "Other")


def build_tables(records, snapshot_ts):
    events, categories, products, substances, rxcuis, presentations = [], [], [], [], [], []

    for r in records:
        sid = make_shortage_id(r)
        package_ndc = r["package_ndc"]

        events.append({
            "shortage_id": sid,
            "package_ndc": package_ndc,
            "product_ndc": "-".join(package_ndc.split("-")[:2]),
            "generic_name_raw": r.get("generic_name"),
            "company_name": r.get("company_name"),
            "status": r.get("status"),
            "availability_raw": r.get("availability"),
            "availability": normalize_availability(r.get("availability")),
            "shortage_reason": r.get("shortage_reason"),
            "dosage_form": r.get("dosage_form"),
            "update_type": r.get("update_type"),
            "related_info": r.get("related_info"),
            "resolved_note": r.get("resolved_note"),
            **{col: r.get(col) for col in DATE_COLUMNS},
            "snapshot_ts": snapshot_ts,
        })
        presentations.append({"shortage_id": sid, "presentation": r.get("presentation")})

        for category in r.get("therapeutic_category", []):
            categories.append({"shortage_id": sid, "therapeutic_category": category})

        fda = r.get("openfda")
        if not fda:
            continue

        products.append({
            "shortage_id": sid,
            "spl_set_id": first(fda.get("spl_set_id")),
            "brand_name": first(fda.get("brand_name")),
            "labeler_name": first(fda.get("manufacturer_name")),
            "application_number": first(fda.get("application_number")),
            "product_type": first(fda.get("product_type")),
        })

        names = fda.get("substance_name", [])
        uniis = fda.get("unii", [])
        if len(names) == len(uniis):
            pairs = zip(names, uniis)
        else:
            pairs = ((name, None) for name in names)
        for name, unii in pairs:
            substances.append({"shortage_id": sid, "substance_name": name, "unii": unii})

        for rxcui in fda.get("rxcui", []):
            rxcuis.append({"shortage_id": sid, "rxcui": rxcui})

    events = pd.DataFrame(events)
    for col in DATE_COLUMNS:
        events[col] = pd.to_datetime(events[col], format="%m/%d/%Y", errors="coerce").dt.date

    tables = {
        "shortage_events": events,
        "shortage_categories": pd.DataFrame(categories),
        "shortage_products": pd.DataFrame(products),
        "shortage_substances": pd.DataFrame(substances),
        "shortage_rxcuis": pd.DataFrame(rxcuis),
        "shortage_presentations": pd.DataFrame(presentations),
    }
    tables = {name: df.drop_duplicates().reset_index(drop=True) for name, df in tables.items()}
    tables["dq_issues"] = build_dq_issues(tables["shortage_presentations"])
    return tables

def build_dq_issues(presentations):
    grouped = presentations.groupby("shortage_id")["presentation"].agg(list)
    multi = grouped[grouped.str.len() > 1]
    return pd.DataFrame({
        "shortage_id": multi.index,
        "issue_type": "multiple_presentations",
        "detail": [" || ".join(map(str, p)) for p in multi],
    })

def validate(tables, records):
    events = tables["shortage_events"]
    dupes = events["shortage_id"].duplicated().sum()
    print(f"Duplicate shortage_ids: {dupes}")
    print(f"Products with more than one row per shortage: {tables['shortage_products']['shortage_id'].duplicated().sum()}")

    unique_records = {make_shortage_id(r): r for r in records}.values()
    print("\nDate parsing:")
    for col in DATE_COLUMNS:
        raw_present = sum(1 for r in unique_records if r.get(col))
        parsed = events[col].notna().sum()
        print(f"  {col}: {parsed} parsed of {raw_present} present")

    print("\nAvailability after cleaning:")
    print(events["availability"].value_counts(dropna=False).to_string())

    print("\nRow counts:")
    for name, df in tables.items():
        print(f"  {name}: {len(df)}")

    print("\nData quality issues:")
    print(tables["dq_issues"].to_string(index=False))

    if dupes:
        raise ValueError("Same shortage_id with different field values. Inspect before continuing.")


def save(tables):
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(SILVER_DIR / f"{name}.parquet", index=False)
    print(f"\nSaved {len(tables)} tables to {SILVER_DIR}")


if __name__ == "__main__":
    records, snapshot_ts = load_latest()
    tables = build_tables(records, snapshot_ts)
    validate(tables, records)
    save(tables)