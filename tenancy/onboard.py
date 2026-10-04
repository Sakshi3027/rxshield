"""Onboard a new hospital: apply its saved mapping, normalize values, match to drug data, report, and load."""
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from ingestion.db import get_engine
from ingestion.ndc import to_ndc11
from tenancy.onboard_mapping import CANONICAL_FIELDS, load_export
from tenancy.setup import ROLES

MAPPINGS_DIR = Path("tenancy/mappings")
DATE_FORMAT = "%m/%d/%y"
MATCH_SQL = """
    select n.ndc11, coalesce(r.drug_rxcui, e.drug_rxcui) as drug_rxcui
    from analytics.stg_concept_ndcs n
    left join analytics.mart_shortage_risk r on r.drug_rxcui = n.concept_rxcui
    left join analytics.stg_drug_equivalents e on e.equivalent_rxcui = n.concept_rxcui
    where n.ndc11 = any(:ndcs)
"""


def normalize_ndc(raw):
    value = raw.strip()
    if not value:
        return None, "missing"
    if "-" in value:
        parts = value.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return None, "bad_format"
        return to_ndc11(value), None
    digits = re.sub(r"\D", "", value)
    if not digits or len(digits) > 11:
        return None, "bad_format"
    return digits.zfill(11), ("restored_zeros" if len(digits) < 11 else None)


def to_number(raw, kind):
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned)) if kind == "int" else float(cleaned)
    except ValueError:
        return None


def normalize(df, mapping):
    report = {"input_rows": len(df)}
    df = df.rename(columns={column: field for field, column in mapping.items() if column})
    df = df[[field for field in CANONICAL_FIELDS if field in df.columns]]

    blank = df.apply(lambda row: all(not str(v).strip() for v in row), axis=1)
    df = df[~blank].copy()
    report["blank_rows_removed"] = int(blank.sum())

    before = len(df)
    df = df.drop_duplicates()
    report["duplicates_removed"] = before - len(df)

    ndc = df["ndc"].map(normalize_ndc)
    df["ndc11"] = ndc.str[0]
    df["ndc_note"] = ndc.str[1]
    report["ndcs_with_restored_zeros"] = int((df["ndc_note"] == "restored_zeros").sum())

    df["drug_name"] = df["drug_name"].str.strip()
    df["on_hand_units"] = df["on_hand_units"].map(lambda v: to_number(v, "int"))
    df["avg_daily_units"] = df["avg_daily_units"].map(lambda v: to_number(v, "float"))
    df["unit_price"] = df["unit_price"].map(lambda v: to_number(v, "float"))
    df["supplier"] = df["supplier"].str.strip().where(df["supplier"].str.strip() != "", None)
    df["contract_end"] = pd.to_datetime(df["contract_end"], format=DATE_FORMAT, errors="coerce").dt.date

    invalid = df["ndc11"].isna() | df["on_hand_units"].isna() | ~(df["avg_daily_units"] > 0)
    report["invalid_rows"] = df.loc[invalid, "drug_name"].tolist()
    return df[~invalid].copy(), report


def match(df, engine):
    lookup = pd.read_sql(text(MATCH_SQL), engine, params={"ndcs": df["ndc11"].tolist()})
    lookup = lookup.dropna(subset=["drug_rxcui"]).drop_duplicates("ndc11")
    merged = df.merge(lookup, on="ndc11", how="left")
    matched = merged[merged["drug_rxcui"].notna()].copy()
    unmatched = merged.loc[merged["drug_rxcui"].isna(), "drug_name"].tolist()
    return matched, unmatched


def load(engine, tenant_id, name, region, matched):
    formulary = matched.groupby("drug_rxcui", as_index=False).agg(
        drug_name=("drug_name", "first"),
        on_hand_units=("on_hand_units", "sum"),
        avg_daily_units=("avg_daily_units", "sum"),
    )
    contracts = matched.dropna(subset=["unit_price", "supplier", "contract_end"]).drop_duplicates("drug_rxcui")

    with engine.begin() as conn:
        conn.execute(text(
            "insert into tenancy.tenants (tenant_id, name, region) values (:t, :n, :r) "
            "on conflict (tenant_id) do update set name = excluded.name, region = excluded.region"),
            {"t": tenant_id, "n": name, "r": region})
        for role in ROLES:
            conn.execute(text(
                "insert into tenancy.users (user_id, tenant_id, display_name, role) "
                "values (:u, :t, :d, :r) on conflict (user_id) do nothing"),
                {"u": f"{tenant_id}-{role}", "t": tenant_id, "d": f"{name.split()[0]} {role.title()}", "r": role})
        conn.execute(text("delete from tenancy.contracts where tenant_id = :t"), {"t": tenant_id})
        conn.execute(text("delete from tenancy.formulary where tenant_id = :t"), {"t": tenant_id})
        conn.execute(text(
            "insert into tenancy.formulary (tenant_id, drug_rxcui, drug_name, on_hand_units, avg_daily_units) "
            "values (:tenant_id, :drug_rxcui, :drug_name, :on_hand_units, :avg_daily_units)"),
            formulary.assign(tenant_id=tenant_id).to_dict("records"))
        conn.execute(text(
            "insert into tenancy.contracts (tenant_id, drug_rxcui, supplier, unit_price, contract_end) "
            "values (:tenant_id, :drug_rxcui, :supplier, :unit_price, :contract_end)"),
            contracts.assign(tenant_id=tenant_id)[
                ["tenant_id", "drug_rxcui", "supplier", "unit_price", "contract_end"]].to_dict("records"))
    return len(formulary), len(contracts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tenant_id, name, region, path = args
    apply = "--apply" in sys.argv
    start = time.perf_counter()

    mapping = json.loads((MAPPINGS_DIR / f"{tenant_id}.json").read_text())["mapping"]
    engine = get_engine()
    clean, report = normalize(load_export(path), mapping)
    matched, unmatched = match(clean, engine)

    print(f"Onboarding report for {name}")
    print(f"  input rows:                 {report['input_rows']}")
    print(f"  blank rows removed:         {report['blank_rows_removed']}")
    print(f"  duplicate rows removed:     {report['duplicates_removed']}")
    print(f"  NDCs with restored zeros:   {report['ndcs_with_restored_zeros']}")
    print(f"  invalid rows:               {len(report['invalid_rows'])} {report['invalid_rows']}")
    print(f"  matched to drug data:       {len(matched)} of {len(clean)}")
    print(f"  unmatched:                  {len(unmatched)}")
    for item in unmatched:
        print(f"    - {item}")

    if not apply:
        print("\nDry run only. Re-run with --apply to load.")
        return
    formulary_rows, contract_rows = load(engine, tenant_id, name, region, matched)
    print(f"\nLoaded {formulary_rows} formulary rows and {contract_rows} contracts "
          f"for {name} in {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()