"""Load every silver Parquet table into the Supabase 'silver' schema."""
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Date, text

from ingestion.db import get_engine

SILVER_DIR = Path("data/silver")
SCHEMA = "silver"


def column_types(df):
    types = {}
    for col in df.columns:
        sample = df[col].dropna()
        if not sample.empty and isinstance(sample.iloc[0], date):
            types[col] = Date()
    return types


def load_table(engine, name, df):
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {SCHEMA}."{name}" CASCADE'))
    df.to_sql(
        name, engine, schema=SCHEMA, if_exists="append", index=False,
        dtype=column_types(df), method="multi", chunksize=1000,
    )
    with engine.connect() as conn:
        loaded = conn.execute(text(f'SELECT count(*) FROM {SCHEMA}."{name}"')).scalar()
    status = "ok" if loaded == len(df) else "MISMATCH"
    print(f"  {name}: {loaded} of {len(df)} rows [{status}]")
    return loaded == len(df)


def main():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))

    paths = sorted(SILVER_DIR.glob("*.parquet"))
    print(f"Loading {len(paths)} tables into schema '{SCHEMA}'")
    results = [load_table(engine, path.stem, pd.read_parquet(path)) for path in paths]

    if not all(results):
        raise ValueError("Row count mismatch between Parquet and Postgres.")
    print("All tables loaded and verified.")


if __name__ == "__main__":
    main()