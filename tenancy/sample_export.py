"""Generate a realistic, messy formulary export for onboarding a new hospital."""
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ingestion.db import get_engine

OUTPUT = Path("data/onboarding/riverbend_formulary_export.csv")
VENDORS = ["McKesson", "Cardinal Health", "Cencora"]


def messy_ndc(ndc11, rng):
    style = rng.choice(["plain", "dashed", "excel"])
    if style == "plain":
        return ndc11
    if style == "dashed":
        return f"{ndc11[:5]}-{ndc11[5:9]}-{ndc11[9:]}"
    return ndc11.lstrip("0")


def main():
    rng = random.Random("riverbend")
    products = pd.read_sql("""
        select distinct on (e.drug_rxcui) n.ndc11, e.equivalent_name as name
        from analytics.stg_drug_equivalents e
        join analytics.stg_concept_ndcs n on n.concept_rxcui = e.equivalent_rxcui
        order by e.drug_rxcui, n.ndc11""", get_engine())

    rows = []
    for p in products.sample(n=120, random_state=7).itertuples():
        daily = round(rng.uniform(2, 60), 1)
        rows.append({
            "Item Description": p.name.upper() if rng.random() < 0.5 else p.name,
            "NDC": messy_ndc(p.ndc11, rng),
            "QOH": f"{int(daily * rng.uniform(1, 45)):,}",
            "Avg Daily Usage": daily,
            "Unit Cost": f"${rng.uniform(2, 400):,.2f}",
            "Primary Vendor": rng.choice(VENDORS),
            "Contract Exp": (date.today() + timedelta(days=rng.randint(30, 720))).strftime("%m/%d/%y"),
        })

    for i in range(6):
        rows.append({
            "Item Description": f"FLOOR STOCK SUPPLY ITEM {i + 1}",
            "NDC": f"99999{rng.randint(100000, 999999)}",
            "QOH": str(rng.randint(10, 500)), "Avg Daily Usage": round(rng.uniform(1, 10), 1),
            "Unit Cost": f"${rng.uniform(1, 20):.2f}", "Primary Vendor": rng.choice(VENDORS),
            "Contract Exp": "",
        })
    rows += rng.sample(rows[:120], 3)
    rows.append({key: "" for key in rows[0]})
    rng.shuffle(rows)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    export = pd.DataFrame(rows)
    export.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(export)} rows to {OUTPUT}\n")
    print(export.head(8).to_string(index=False))


if __name__ == "__main__":
    main()