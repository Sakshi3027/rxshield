"""Parse the latest DECRS registration file into a facilities silver table and link it to SPL establishments."""
import zipfile
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/decrs")
SILVER_DIR = Path("data/silver")

KEEP_COLUMNS = {
    "FEI_NUMBER": "fei",
    "DUNS_NUMBER": "duns",
    "FIRM_NAME": "firm_name",
    "ADDRESS": "address",
    "EXPIRATION_DATE": "registration_expires",
    "OPERATIONS": "registered_operations",
    "REGISTRANT_NAME": "registrant_name",
    "REGISTRANT_DUNS": "registrant_duns",
}

COUNTRY_OVERRIDES = {"KOR": "South Korea"}

def load_latest():
    latest = sorted(RAW_DIR.glob("decrs_*.zip"))[-1]
    with zipfile.ZipFile(latest) as zf:
        with zf.open("drls_reg.txt") as f:
            raw = pd.read_csv(f, sep="\t", encoding="latin-1", dtype=str, index_col=False)
    return raw, latest.stem.replace("decrs_", "")


def build_facilities(raw, snapshot_ts):
    raw.columns = [c.strip() for c in raw.columns]
    df = raw[list(KEEP_COLUMNS)].rename(columns=KEEP_COLUMNS)
    df = df.apply(lambda col: col.str.strip())
    df["country_code"] = df["address"].str.extract(r"\(([A-Z]{3})\)\s*$")[0]
    text_names = df["address"].str.extract(r",\s*([^,]+?)\s*\([A-Z]{3}\)\s*$")[0]
    lookup = text_names.groupby(df["country_code"]).agg(lambda names: names.mode().iat[0])
    lookup.update(pd.Series(COUNTRY_OVERRIDES))
    df["country"] = df["country_code"].map(lookup)
    df["registration_expires"] = pd.to_datetime(
        df["registration_expires"], format="%m/%d/%Y", errors="coerce"
    ).dt.date
    df["snapshot_ts"] = snapshot_ts
    return df.drop_duplicates().reset_index(drop=True)


def validate(facilities):
    print(f"Registered establishments: {len(facilities)}")
    print(f"Duplicate DUNS: {facilities['duns'].duplicated().sum()}")
    print(f"Missing country code: {facilities['country_code'].isna().sum()}")
    print("\nTop countries:")
    print(facilities["country"].value_counts().head(8).to_string())

    ops = pd.read_parquet(SILVER_DIR / "establishment_operations.parquet")
    spl_duns = set(ops["establishment_duns"])
    matched = spl_duns & set(facilities["duns"])
    print(f"\nSPL establishments found in DECRS: {len(matched)} of {len(spl_duns)}")

    shortage_products = set(pd.read_parquet(SILVER_DIR / "shortage_events.parquet")["product_ndc"])
    manufacture = ops[(ops["operation"] == "MANUFACTURE") & ops["product_ndc"].isin(shortage_products)]
    manufacture = manufacture.merge(
        facilities[["duns", "country"]], left_on="establishment_duns", right_on="duns", how="left"
    )

    print("\nShortage products by manufacturing country:")
    by_country = manufacture.groupby("country", dropna=False)["product_ndc"].nunique()
    print(by_country.sort_values(ascending=False).head(10).to_string())

    site_counts = manufacture.groupby("product_ndc")["establishment_duns"].nunique()
    single_site = site_counts[site_counts == 1].index
    print(f"\nSingle-site shortage products by country ({len(single_site)} total):")
    single_by_country = (
        manufacture[manufacture["product_ndc"].isin(single_site)]
        .groupby("country", dropna=False)["product_ndc"].nunique()
    )
    print(single_by_country.sort_values(ascending=False).head(8).to_string())


def main():
    raw, snapshot_ts = load_latest()
    facilities = build_facilities(raw, snapshot_ts)
    validate(facilities)
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    facilities.to_parquet(SILVER_DIR / "facilities.parquet", index=False)
    print(f"\nSaved facilities ({len(facilities)})")


if __name__ == "__main__":
    main()