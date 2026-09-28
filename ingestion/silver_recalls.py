"""Transform the latest bronze recall snapshot into clean silver tables."""
import json
from pathlib import Path

import pandas as pd

from ingestion.ndc import extract_ndcs, to_product_ndc

RAW_DIR = Path("data/raw/recalls")
SILVER_DIR = Path("data/silver")

DATE_COLUMNS = ["recall_initiation_date", "report_date", "center_classification_date", "termination_date"]
TEXT_FIELDS = ["product_description", "code_info", "more_code_info"]
KEEP_COLUMNS = [
    "recall_number", "event_id", "recalling_firm", "classification", "status",
    "voluntary_mandated", "reason_for_recall", "product_description",
    "product_quantity", "distribution_pattern", "city", "state", "country",
]
REASON_FLAGS = {
    "reason_cgmp": "cgmp",
    "reason_sterility": "sterility",
    "reason_contamination": "contamina",
    "reason_particulate": "particulate",
    "reason_subpotent": "subpotent",
    "reason_superpotent": "superpotent",
    "reason_impurity": "impurit",
    "reason_dissolution": "dissolution",
    "reason_labeling": "label",
    "reason_nitrosamine": "nitrosamine",
}


def load_latest():
    latest = sorted(RAW_DIR.glob("recalls_*.json"))[-1]
    snapshot_ts = latest.stem.replace("recalls_", "")
    return json.loads(latest.read_text()), snapshot_ts


def build_tables(records, snapshot_ts):
    events, products = [], []

    for r in records:
        row = {col: r.get(col) for col in KEEP_COLUMNS + DATE_COLUMNS}
        reason = (r.get("reason_for_recall") or "").lower()
        for flag, keyword in REASON_FLAGS.items():
            row[flag] = keyword in reason
        row["snapshot_ts"] = snapshot_ts
        events.append(row)

        text = " ".join(r.get(f) or "" for f in TEXT_FIELDS)
        for package_ndc in extract_ndcs(text):
            products.append({
                "recall_number": r["recall_number"],
                "product_ndc": to_product_ndc(package_ndc),
                "package_ndc": package_ndc,
                "link_method": "text",
            })

        for product_ndc in r.get("openfda", {}).get("product_ndc", []):
            products.append({
                "recall_number": r["recall_number"],
                "product_ndc": product_ndc,
                "package_ndc": None,
                "link_method": "openfda",
            })

    events = pd.DataFrame(events)
    for col in DATE_COLUMNS:
        events[col] = pd.to_datetime(events[col], format="%Y%m%d", errors="coerce").dt.date

    tables = {
        "recall_events": events,
        "recall_products": pd.DataFrame(products),
    }
    return {name: df.drop_duplicates().reset_index(drop=True) for name, df in tables.items()}


def validate(tables, records):
    events = tables["recall_events"]
    dupes = events["recall_number"].duplicated().sum()
    print(f"Duplicate recall_numbers: {dupes}")

    unique_records = {r["recall_number"]: r for r in records}.values()
    print("\nDate parsing:")
    for col in DATE_COLUMNS:
        raw_present = sum(1 for r in unique_records if r.get(col))
        parsed = events[col].notna().sum()
        print(f"  {col}: {parsed} parsed of {raw_present} present")

    print("\nReason flags:")
    for flag in REASON_FLAGS:
        print(f"  {flag}: {events[flag].sum()}")

    products = tables["recall_products"]
    print("\nProduct links by method:")
    print(products["link_method"].value_counts().to_string())
    print(f"Recalls with at least one product link: {products['recall_number'].nunique()} of {len(events)}")

    print("\nRow counts:")
    for name, df in tables.items():
        print(f"  {name}: {len(df)}")

    if dupes:
        raise ValueError("Same recall_number with different field values. Inspect before continuing.")


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