"""Parse DailyMed SPL labels into labeler and establishment-operation silver tables."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

V = "{urn:hl7-org:v3}"
DUNS_ROOT = "1.3.6.1.4.1.519.1"
RAW_DIR = Path("data/raw/spl")
SILVER_DIR = Path("data/silver")


def org_identity(org):
    if org is None:
        return None, None
    name = org.findtext(f"{V}name")
    duns = next((i.get("extension") for i in org.findall(f"{V}id") if i.get("root") == DUNS_ROOT), None)
    return (name.strip() if name else None), duns


def operation_name(code):
    if code is None:
        return None
    value = code.get("displayName") or code.get("code")
    return value.upper() if value else None


def parse_label(path):
    root = ET.parse(path).getroot()
    set_id = path.stem

    effective = root.find(f"{V}effectiveTime")
    labeler = root.find(f"{V}author/{V}assignedEntity/{V}representedOrganization")
    labeler_name, labeler_duns = org_identity(labeler)

    operations = []
    for entity in root.iter(f"{V}assignedEntity"):
        performances = entity.findall(f"{V}performance")
        if not performances:
            continue
        org = entity.find(f"{V}assignedOrganization")
        name, duns = org_identity(org)

        for perf in performances:
            product = perf.find(f".//{V}manufacturedMaterialKind/{V}code")
            operations.append({
                "spl_set_id": set_id,
                "establishment_duns": duns,
                "establishment_name": name,
                "operation": operation_name(perf.find(f"{V}actDefinition/{V}code")),
                "product_ndc": product.get("code") if product is not None else None,
            })

    label = {
        "spl_set_id": set_id,
        "labeler_name": labeler_name,
        "labeler_duns": labeler_duns,
        "label_effective_date": effective.get("value")[:8] if effective is not None else None,
    }
    return label, operations


def validate(labels, operations, failures):
    print(f"Labels parsed: {len(labels)}, failed: {len(failures)}")
    no_establishments = (~labels["spl_set_id"].isin(operations["spl_set_id"])).sum()
    print(f"Labels with no establishment section: {no_establishments}")
    print(f"Distinct establishments (by DUNS): {operations['establishment_duns'].nunique()}")
    print(f"Operations missing DUNS: {operations['establishment_duns'].isna().sum()}")

    print("\nOperation types:")
    print(operations["operation"].value_counts().to_string())

    shortage_products = set(pd.read_parquet(SILVER_DIR / "shortage_events.parquet")["product_ndc"])
    manufacture = operations[
        (operations["operation"] == "MANUFACTURE") & operations["product_ndc"].isin(shortage_products)
    ]
    sites_per_product = manufacture.groupby("product_ndc")["establishment_duns"].nunique()
    print(f"\nShortage products with a known manufacturing site: {len(sites_per_product)} of {len(shortage_products)}")
    print(f"  made at exactly one site: {(sites_per_product == 1).sum()}")
    print(f"  made at two or more sites: {(sites_per_product >= 2).sum()}")

    print("\nSites manufacturing the most shortage products:")
    top = manufacture.groupby("establishment_name")["product_ndc"].nunique().sort_values(ascending=False).head(10)
    print(top.to_string())

    if failures:
        print(f"\nFailed labels: {failures[:5]}")


def main():
    labels, operations, failures = [], [], []
    for path in sorted(RAW_DIR.glob("*.xml")):
        try:
            label, ops = parse_label(path)
        except ET.ParseError as err:
            failures.append((path.stem, str(err)))
            continue
        labels.append(label)
        operations.extend(ops)

    labels = pd.DataFrame(labels)
    labels["label_effective_date"] = pd.to_datetime(
        labels["label_effective_date"], format="%Y%m%d", errors="coerce"
    ).dt.date
    operations = pd.DataFrame(operations).drop_duplicates().reset_index(drop=True)

    validate(labels, operations, failures)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(SILVER_DIR / "spl_labels.parquet", index=False)
    operations.to_parquet(SILVER_DIR / "establishment_operations.parquet", index=False)
    print(f"\nSaved spl_labels ({len(labels)}) and establishment_operations ({len(operations)})")


if __name__ == "__main__":
    main()