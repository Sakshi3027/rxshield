"""Single-point-of-failure analysis: what breaks if a facility, company, or country goes offline."""
from collections import defaultdict

import pandas as pd
from sqlalchemy import text

from graph.build_graph import to_rows
from graph.db import get_driver
from ingestion.db import get_engine

DEPENDENCY_QUERY = """
MATCH (d:Drug)<-[:IS_DRUG]-(:Package)-[:OF_PRODUCT]->(:Product)<-[:MANUFACTURES]-(f:Facility)
MATCH (f)-[:LOCATED_IN]->(c:Country)
MATCH (f)-[:OWNED_BY]->(co:Company)
RETURN DISTINCT d.rxcui AS drug, d.risk_tier AS tier, d.has_current_shortage AS current,
       f.duns AS facility, f.name AS facility_name,
       co.duns AS company, co.name AS company_name,
       c.code AS country, c.name AS country_name
"""

LEVELS = {
    "Facility": ("facility", "facility_name", "duns"),
    "Company": ("company", "company_name", "duns"),
    "Country": ("country", "country_name", "code"),
}


def simulate(df, id_col, name_col):
    drug_entities = df.groupby("drug")[id_col].agg(set)
    drug_info = df.drop_duplicates("drug").set_index("drug")
    names = df.drop_duplicates(id_col).set_index(id_col)[name_col]

    stats = defaultdict(lambda: {
        "drugs_dependent": 0, "drugs_lost": 0,
        "current_shortage_drugs_lost": 0, "critical_or_high_drugs_lost": 0,
    })
    for drug, entities in drug_entities.items():
        for entity in entities:
            stats[entity]["drugs_dependent"] += 1
        if len(entities) == 1:
            entity = next(iter(entities))
            stats[entity]["drugs_lost"] += 1
            stats[entity]["current_shortage_drugs_lost"] += int(bool(drug_info.at[drug, "current"]))
            stats[entity]["critical_or_high_drugs_lost"] += int(drug_info.at[drug, "tier"] in ("critical", "high"))

    rows = [{"entity_id": e, "entity_name": names[e], **s} for e, s in stats.items()]
    return pd.DataFrame(rows).sort_values("drugs_lost", ascending=False)


def main():
    with get_driver() as driver:
        records, _, _ = driver.execute_query(DEPENDENCY_QUERY)
        df = pd.DataFrame([r.data() for r in records])
        print(f"{df['drug'].nunique()} drugs with known manufacturing sites")
        driver.execute_query(
            "MATCH (n) WHERE n:Facility OR n:Company OR n:Country "
            "SET n.drugs_dependent = 0, n.drugs_lost_if_offline = 0, "
            "n.current_shortage_drugs_lost = 0, n.critical_or_high_drugs_lost = 0")

        results = []
        for label, (id_col, name_col, key) in LEVELS.items():
            impact = simulate(df, id_col, name_col)
            driver.execute_query(
                f"UNWIND $rows AS row MATCH (n:{label} {{{key}: row.entity_id}}) "
                "SET n.drugs_dependent = row.drugs_dependent, "
                "n.drugs_lost_if_offline = row.drugs_lost, "
                "n.current_shortage_drugs_lost = row.current_shortage_drugs_lost, "
                "n.critical_or_high_drugs_lost = row.critical_or_high_drugs_lost",
                rows=to_rows(impact),
            )
            impact.insert(0, "entity_type", label)
            results.append(impact)

            print(f"\nTop {label} single points of failure:")
            cols = ["entity_name", "drugs_dependent", "drugs_lost", "critical_or_high_drugs_lost"]
            print(impact.head(5)[cols].to_string(index=False))

    combined = pd.concat(results, ignore_index=True)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS graph_analytics"))
        conn.execute(text("DROP TABLE IF EXISTS graph_analytics.failure_impact CASCADE"))
    combined.to_sql("failure_impact", engine, schema="graph_analytics", if_exists="append", index=False)
    print(f"\nSaved {len(combined)} rows to graph_analytics.failure_impact")


if __name__ == "__main__":
    main()