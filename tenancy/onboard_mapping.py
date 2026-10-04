"""Profile a hospital export, have an LLM propose a column mapping, and save it after human review."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from groq import Groq

load_dotenv(".env")

MODEL = "openai/gpt-oss-20b"
MAPPINGS_DIR = Path("tenancy/mappings")
CANONICAL_FIELDS = {
    "drug_name": "Human-readable product description",
    "ndc": "National Drug Code identifying the package",
    "on_hand_units": "Quantity currently in stock",
    "avg_daily_units": "Average units used per day",
    "unit_price": "Contract or acquisition cost per unit",
    "supplier": "Vendor or wholesaler supplying the product",
    "contract_end": "Date the supply contract expires",
}
REQUIRED = {"drug_name", "ndc", "on_hand_units", "avg_daily_units"}
SYSTEM_PROMPT = """You map columns from a hospital pharmacy export to a canonical schema.
Judge each column by both its name and its example values.
Return only JSON in this exact shape:
{"mapping": {"<canonical_field>": {"column": "<source column name or null>",
                                   "confidence": "high|medium|low", "reason": "<short reason>"}}}
Include every canonical field. Use each source column at most once. Use null when no column fits."""


def load_export(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def profile(df):
    lines = []
    for column in df.columns:
        values = df[column].str.strip()
        values = values[values != ""]
        examples = values.drop_duplicates().head(5).tolist()
        lines.append(f"- {column!r}: {len(values)} non-empty values, examples {examples}")
    return "\n".join(lines)


def propose_mapping(df):
    fields = "\n".join(f"- {name}: {desc}" for name, desc in CANONICAL_FIELDS.items())
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Canonical fields:\n{fields}\n\nExport columns:\n{profile(df)}"},
        ],
    )
    return json.loads(response.choices[0].message.content)["mapping"]


def validate_mapping(mapping, df):
    problems = []
    used = [m["column"] for m in mapping.values() if m.get("column")]
    for field in CANONICAL_FIELDS:
        if field not in mapping:
            problems.append(f"missing field {field}")
    for column in used:
        if column not in df.columns:
            problems.append(f"unknown column {column!r}")
    if len(used) != len(set(used)):
        problems.append("a source column is mapped to more than one field")
    for field in REQUIRED:
        if not mapping.get(field, {}).get("column"):
            problems.append(f"required field {field} has no column")
    return problems


def main():
    tenant_id, path = sys.argv[1], Path(sys.argv[2])
    df = load_export(path)
    print(f"Profiled {len(df)} rows, {len(df.columns)} columns from {path.name}\n")

    mapping = propose_mapping(df)
    print(f"{'field':<17} {'source column':<20} {'confidence':<10} reason")
    for field in CANONICAL_FIELDS:
        m = mapping.get(field, {})
        print(f"{field:<17} {str(m.get('column')):<20} {m.get('confidence', ''):<10} {m.get('reason', '')}")

    problems = validate_mapping(mapping, df)
    if problems:
        print("\nMapping rejected:\n  " + "\n  ".join(problems))
        return

    if input("\nApply this mapping? [y/N] ").strip().lower() != "y":
        print("Not saved.")
        return

    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    saved = {"tenant_id": tenant_id, "source_file": path.name,
             "mapping": {field: mapping[field]["column"] for field in CANONICAL_FIELDS}}
    out = MAPPINGS_DIR / f"{tenant_id}.json"
    out.write_text(json.dumps(saved, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()