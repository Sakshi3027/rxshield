"""Parse cached RxNav responses into RxNorm silver tables."""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/rxnorm")
SILVER_DIR = Path("data/silver")


def read_all(kind):
    for path in sorted((RAW_DIR / kind).glob("*.json")):
        yield path.stem, json.loads(path.read_text())


def build_package_rxcui():
    rows = []
    for ndc, data in read_all("ndcstatus"):
        status = data.get("ndcStatus", {})
        rows.append({
            "package_ndc": ndc,
            "rxcui": status.get("rxcui") or None,
            "concept_name": status.get("conceptName") or None,
            "ndc_status": status.get("status") or None,
        })
    return pd.DataFrame(rows)


def build_drug_concepts():
    rows = []
    for rxcui, data in read_all("related"):
        for group in data.get("relatedGroup", {}).get("conceptGroup", []):
            for concept in group.get("conceptProperties", []):
                rows.append({
                    "drug_rxcui": rxcui,
                    "related_tty": concept["tty"],
                    "related_rxcui": concept["rxcui"],
                    "related_name": concept["name"],
                })
    return pd.DataFrame(rows)


def build_ingredient_atc():
    rows = []
    for ingredient, data in read_all("atc"):
        for item in data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", []):
            concept = item["minConcept"]
            if concept["rxcui"] != ingredient:
                continue
            atc = item["rxclassMinConceptItem"]
            rows.append({
                "ingredient_rxcui": ingredient,
                "ingredient_name": concept["name"],
                "atc_code": atc["classId"],
                "atc_name": atc["className"],
                "atc3_code": atc["classId"][:4],
            })
    return pd.DataFrame(rows)


def validate(tables):
    pkg = tables["package_rxcui"]
    print(f"Packages: {len(pkg)}, with RxCUI: {pkg['rxcui'].notna().sum()}")
    print("\nNDC status:")
    print(pkg["ndc_status"].value_counts(dropna=False).to_string())
    print(f"\nUnmapped packages: {pkg.loc[pkg['rxcui'].isna(), 'package_ndc'].tolist()}")

    concepts = tables["drug_concepts"]
    print("\nRelated concepts by type:")
    print(concepts["related_tty"].value_counts().to_string())
    ingredient_links = concepts[concepts["related_tty"] == "IN"]
    per_drug = ingredient_links.groupby("drug_rxcui").size()
    print(f"Drugs with no ingredient: {len(set(pkg['rxcui'].dropna()) - set(per_drug.index))}")
    print(f"Combination drugs (2+ ingredients): {(per_drug >= 2).sum()}")

    atc = tables["ingredient_atc"]
    ingredients = set(ingredient_links["related_rxcui"])
    print(f"\nIngredients with an ATC class: {atc['ingredient_rxcui'].nunique()} of {len(ingredients)}")

    joined = (
        pkg.dropna(subset=["rxcui"])
        .merge(ingredient_links, left_on="rxcui", right_on="drug_rxcui")
        .merge(atc, left_on="related_rxcui", right_on="ingredient_rxcui")
    )
    print("\nTherapeutic classes with the most shortage packages:")
    top = joined.groupby(["atc_code", "atc_name"])["package_ndc"].nunique().sort_values(ascending=False).head(10)
    print(top.to_string())


def main():
    tables = {
        "package_rxcui": build_package_rxcui(),
        "drug_concepts": build_drug_concepts(),
        "ingredient_atc": build_ingredient_atc(),
    }
    tables = {name: df.drop_duplicates().reset_index(drop=True) for name, df in tables.items()}
    validate(tables)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(SILVER_DIR / f"{name}.parquet", index=False)
    print(f"\nSaved {', '.join(f'{n} ({len(d)})' for n, d in tables.items())}")


if __name__ == "__main__":
    main()