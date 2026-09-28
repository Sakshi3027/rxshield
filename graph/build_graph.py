"""Build the RxShield knowledge graph in Neo4j from the dbt analytics layer."""
import pandas as pd

from graph.db import get_driver
from ingestion.db import get_engine

BATCH_SIZE = 1000
A = "analytics"
SHORTAGE_PRODUCTS = f"select product_ndc from {A}.mart_product_manufacturing"

NODES = [
    ("Drug", "rxcui", f"""
        select equivalent_rxcui as rxcui, min(equivalent_name) as name, bool_or(is_brand) as is_brand
        from {A}.stg_drug_equivalents
        where equivalent_rxcui not in (select drug_rxcui from {A}.mart_shortage_risk)
        group by equivalent_rxcui"""),
    ("Drug", "rxcui", f"""
        select drug_rxcui as rxcui, drug_name as name, is_pack, has_current_shortage,
               alternative_status, alternative_labeler_count, manufacturing_site_count,
               risk_tier, risk_reasons
        from {A}.mart_shortage_risk"""),
    ("Package", "package_ndc", f"select package_ndc, ndc_status from {A}.stg_package_drugs"),
    ("Product", "product_ndc", f"""
        select product_ndc, generic_name, company_name, sourcing_status, manufacturing_site_count
        from {A}.mart_product_manufacturing"""),
    ("Shortage", "shortage_id", f"""
        select shortage_id, status, availability, shortage_reason as reason,
               initial_posting_date::text as initial_posting_date, update_date::text as update_date
        from {A}.stg_shortage_events"""),
    ("Facility", "duns", f"""
        select duns, fei, firm_name as name, country, country_code
        from {A}.stg_facilities
        where duns in (select duns from {A}.stg_establishment_operations)"""),
    ("Country", "code", f"""
        select distinct country_code as code, country as name
        from {A}.stg_facilities
        where duns in (select duns from {A}.stg_establishment_operations)"""),
    ("Ingredient", "rxcui", f"""
        select distinct ingredient_rxcui as rxcui, ingredient_name as name
        from {A}.stg_drug_ingredients"""),
    ("AtcClass", "code", f"select distinct atc_code as code, atc_name as name from {A}.stg_ingredient_atc"),
    ("DoseFormGroup", "rxcui", f"""
        select distinct dose_form_group_rxcui as rxcui, dose_form_group_name as name
        from {A}.stg_drug_dose_forms"""),
    ("Recall", "recall_number", f"""
        select distinct re.recall_number, re.classification, re.reason_for_recall as reason,
               re.recall_initiation_date::text as initiation_date, re.recall_status as status,
               re.recalling_firm as firm
        from {A}.stg_recall_events re
        join {A}.stg_recall_products rp on rp.recall_number = re.recall_number
        where rp.product_ndc in ({SHORTAGE_PRODUCTS})"""),

    ("Company", "duns", f"""
        select company_duns as duns, company_name as name, facility_count, countries,
               shortage_products_manufactured, sole_company_products
        from {A}.mart_company_exposure"""),
]

RELATIONSHIPS = [
    ("AFFECTS", f"select shortage_id, package_ndc from {A}.stg_shortage_events",
     "MATCH (a:Shortage {shortage_id: row.shortage_id}) MATCH (b:Package {package_ndc: row.package_ndc}) "
     "MERGE (a)-[:AFFECTS]->(b)"),
    ("OF_PRODUCT", f"select distinct package_ndc, product_ndc from {A}.stg_shortage_events",
     "MATCH (a:Package {package_ndc: row.package_ndc}) MATCH (b:Product {product_ndc: row.product_ndc}) "
     "MERGE (a)-[:OF_PRODUCT]->(b)"),
    ("IS_DRUG", f"select package_ndc, drug_rxcui from {A}.stg_package_drugs where drug_rxcui is not null",
     "MATCH (a:Package {package_ndc: row.package_ndc}) MATCH (b:Drug {rxcui: row.drug_rxcui}) "
     "MERGE (a)-[:IS_DRUG]->(b)"),
    ("LOCATED_IN", f"""select duns, country_code from {A}.stg_facilities
        where duns in (select duns from {A}.stg_establishment_operations)""",
     "MATCH (a:Facility {duns: row.duns}) MATCH (b:Country {code: row.country_code}) "
     "MERGE (a)-[:LOCATED_IN]->(b)"),
    ("HAS_INGREDIENT", f"select drug_rxcui, ingredient_rxcui from {A}.stg_drug_ingredients",
     "MATCH (a:Drug {rxcui: row.drug_rxcui}) MATCH (b:Ingredient {rxcui: row.ingredient_rxcui}) "
     "MERGE (a)-[:HAS_INGREDIENT]->(b)"),
    ("IN_CLASS", f"select ingredient_rxcui, atc_code from {A}.stg_ingredient_atc",
     "MATCH (a:Ingredient {rxcui: row.ingredient_rxcui}) MATCH (b:AtcClass {code: row.atc_code}) "
     "MERGE (a)-[:IN_CLASS]->(b)"),
    ("HAS_DOSE_FORM", f"select drug_rxcui, dose_form_group_rxcui from {A}.stg_drug_dose_forms",
     "MATCH (a:Drug {rxcui: row.drug_rxcui}) MATCH (b:DoseFormGroup {rxcui: row.dose_form_group_rxcui}) "
     "MERGE (a)-[:HAS_DOSE_FORM]->(b)"),
    ("EQUIVALENT_TO", f"""select drug_rxcui, equivalent_rxcui from {A}.stg_drug_equivalents
        where drug_rxcui <> equivalent_rxcui""",
     "MATCH (a:Drug {rxcui: row.drug_rxcui}) MATCH (b:Drug {rxcui: row.equivalent_rxcui}) "
     "MERGE (a)-[:EQUIVALENT_TO]->(b)"),
    ("RECALLED", f"""select recall_number, product_ndc, linked_by_text, linked_by_openfda
        from {A}.stg_recall_products where product_ndc in ({SHORTAGE_PRODUCTS})""",
     "MATCH (a:Recall {recall_number: row.recall_number}) MATCH (b:Product {product_ndc: row.product_ndc}) "
     "MERGE (a)-[r:RECALLED]->(b) "
     "SET r.linked_by_text = row.linked_by_text, r.linked_by_openfda = row.linked_by_openfda"),
    ("OWNED_BY", f"""select duns, coalesce(registrant_duns, duns) as company_duns
        from {A}.stg_facilities
        where duns in (select duns from {A}.stg_establishment_operations)""",
     "MATCH (a:Facility {duns: row.duns}) MATCH (b:Company {duns: row.company_duns}) "
     "MERGE (a)-[:OWNED_BY]->(b)"),
]

OPERATION_TYPES = {
    "MANUFACTURE": "MANUFACTURES",
    "API MANUFACTURE": "MANUFACTURES_API",
    "PACK": "PACKAGES",
    "LABEL": "LABELS",
    "ANALYSIS": "TESTS",
    "STERILIZE": "STERILIZES",
    "PARTICLE SIZE REDUCTION": "PROCESSES",
}
for operation, rel_type in OPERATION_TYPES.items():
    RELATIONSHIPS.append((
        rel_type,
        f"""select duns, product_ndc from {A}.stg_establishment_operations
            where operation = '{operation}' and product_ndc in ({SHORTAGE_PRODUCTS})""",
        f"MATCH (a:Facility {{duns: row.duns}}) MATCH (b:Product {{product_ndc: row.product_ndc}}) "
        f"MERGE (a)-[:{rel_type}]->(b)",
    ))


def to_rows(df):
    return df.convert_dtypes().astype(object).where(df.notna(), None).to_dict("records")


def run_batches(driver, cypher, rows):
    written = 0
    for start in range(0, len(rows), BATCH_SIZE):
        records, _, _ = driver.execute_query(
            f"UNWIND $rows AS row {cypher} RETURN count(*) AS written",
            rows=rows[start:start + BATCH_SIZE],
        )
        written += records[0]["written"]
    return written


def main():
    engine = get_engine()
    with get_driver() as driver:
        print("Clearing existing graph")
        driver.execute_query("MATCH (n) DETACH DELETE n")

        for label, key in {(label, key) for label, key, _ in NODES}:
            driver.execute_query(
                f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            )

        print("\nNodes:")
        for label, key, sql in NODES:
            rows = to_rows(pd.read_sql(sql, engine))
            cypher = f"MERGE (n:{label} {{{key}: row.{key}}}) SET n += row"
            print(f"  {label}: {run_batches(driver, cypher, rows)}")

        print("\nRelationships:")
        problems = 0
        for rel_type, sql, cypher in RELATIONSHIPS:
            rows = to_rows(pd.read_sql(sql, engine))
            written = run_batches(driver, cypher, rows)
            flag = "" if written == len(rows) else f"  <-- {len(rows) - written} rows had missing endpoints"
            problems += written != len(rows)
            print(f"  {rel_type}: {written} of {len(rows)}{flag}")

        print("\nGraph totals:")
        records, _, _ = driver.execute_query(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"
        )
        for record in records:
            print(f"  {record['label']}: {record['count']}")

        if problems:
            raise ValueError(f"{problems} relationship types had rows with missing endpoints.")


if __name__ == "__main__":
    main()