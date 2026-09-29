"""Text2Cypher: turn a question into a safe, read-only Cypher query and run it."""
import os
import re
import sys

from dotenv import load_dotenv
from groq import Groq
from neo4j import RoutingControl

from graph.db import get_driver

load_dotenv(".env")

MODEL = "openai/gpt-oss-120b"
MAX_ROWS = 50
FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL|FOREACH)\b", re.IGNORECASE
)

READ_START = re.compile(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN)\b", re.IGNORECASE)
NO_QUERY = "NO_QUERY"


class NotAnswerable(Exception):
    pass

SCHEMA = """Graph schema (Neo4j):

Nodes and properties:
- Drug {rxcui, name, is_pack, has_current_shortage (boolean), risk_tier ('critical'|'high'|'elevated'|'watch'),
  risk_reasons, alternative_status ('no_listed_alternative'|'single_alternative'|'multiple_alternatives'),
  alternative_labeler_count, manufacturing_site_count}
  Shortage fields (risk_tier, has_current_shortage, alternative_status) exist only on drugs in shortage.
  Other Drug nodes are equivalents from other manufacturers and have {rxcui, name, is_brand}.
- Package {package_ndc, ndc_status}
- Product {product_ndc, generic_name, company_name, sourcing_status ('single_site'|'multi_site'|'unknown'),
  manufacturing_site_count}
- Shortage {shortage_id, status ('Current'|'To Be Discontinued'|'Resolved'), availability, reason,
  initial_posting_date, update_date}
- Facility {duns, fei, name, country, country_code, drugs_dependent, drugs_lost_if_offline,
  current_shortage_drugs_lost, critical_or_high_drugs_lost}
- Company {duns, name, facility_count, countries, shortage_products_manufactured, sole_company_products,
  drugs_dependent, drugs_lost_if_offline, critical_or_high_drugs_lost}
- Country {code (ISO 3166 alpha-3, e.g. 'USA', 'IND', 'CHN', 'DEU'), name, drugs_dependent,
  drugs_lost_if_offline, critical_or_high_drugs_lost}
- Ingredient {rxcui, name (lowercase, e.g. 'bupivacaine', 'morphine')}
- AtcClass {code, name}
- DoseFormGroup {rxcui, name}
- Recall {recall_number, classification ('Class I'|'Class II'|'Class III'), reason,
  initiation_date (string 'YYYY-MM-DD'), status, firm}
- Label {spl_set_id, labeler_name, effective_date}

Relationships:
- (Shortage)-[:AFFECTS]->(Package)
- (Package)-[:OF_PRODUCT]->(Product)
- (Package)-[:IS_DRUG]->(Drug)
- (Facility)-[:MANUFACTURES|MANUFACTURES_API|PACKAGES|LABELS|TESTS|STERILIZES|PROCESSES]->(Product)
- (Facility)-[:LOCATED_IN]->(Country)
- (Facility)-[:OWNED_BY]->(Company)
- (Drug)-[:HAS_INGREDIENT]->(Ingredient)-[:IN_CLASS]->(AtcClass)
- (Drug)-[:HAS_DOSE_FORM]->(DoseFormGroup)
- (Drug)-[:EQUIVALENT_TO]->(Drug)
- (Recall)-[:RECALLED]->(Product)
- (Label)-[:DESCRIBES]->(Product)"""

EXAMPLES = """Examples:

Question: Which high risk shortage drugs are manufactured only in China?
Cypher:
MATCH (d:Drug {risk_tier: 'high'})<-[:IS_DRUG]-(:Package)-[:OF_PRODUCT]->(:Product)<-[:MANUFACTURES]-(f:Facility)-[:LOCATED_IN]->(c:Country)
WITH d, collect(DISTINCT c.code) AS countries, collect(DISTINCT f.name) AS facilities
WHERE countries = ['CHN']
OPTIONAL MATCH (d)<-[:IS_DRUG]-(:Package)-[:OF_PRODUCT]->(:Product)<-[:DESCRIBES]-(l:Label)
RETURN d.rxcui AS rxcui, d.name AS drug, d.risk_tier AS risk_tier, facilities, collect(DISTINCT l.spl_set_id) AS spl_set_ids
LIMIT 25

Question: What depends on Baxter's plants?
Cypher:
MATCH (co:Company)<-[:OWNED_BY]-(:Facility)-[:MANUFACTURES]->(:Product)<-[:OF_PRODUCT]-(:Package)-[:IS_DRUG]->(d:Drug)
WHERE toLower(co.name) CONTAINS 'baxter'
RETURN co.name AS company, co.drugs_lost_if_offline AS drugs_lost_if_offline, count(DISTINCT d) AS dependent_drugs, collect(DISTINCT d.name)[..15] AS sample_drugs
LIMIT 10

Question: What alternatives exist for dopamine?
Cypher:
MATCH (d:Drug)-[:HAS_INGREDIENT]->(i:Ingredient)
WHERE toLower(i.name) CONTAINS 'dopamine' AND d.risk_tier IS NOT NULL
OPTIONAL MATCH (d)-[:EQUIVALENT_TO]->(e:Drug)
RETURN d.name AS drug, d.risk_tier AS risk_tier, d.alternative_status AS alternative_status, d.alternative_labeler_count AS alternative_sources, collect(DISTINCT e.name)[..10] AS equivalents
LIMIT 25

Question: How should heparin be stored?
Cypher:
MATCH (d:Drug)-[:HAS_INGREDIENT]->(i:Ingredient)
WHERE toLower(i.name) CONTAINS 'heparin'
MATCH (d)<-[:IS_DRUG]-(:Package)-[:OF_PRODUCT]->(:Product)<-[:DESCRIBES]-(l:Label)
RETURN collect(DISTINCT d.name)[..10] AS drugs, collect(DISTINCT l.spl_set_id) AS spl_set_ids
LIMIT 1

Question: Which drugs currently in shortage had Class I recalls in the last 5 years?
Cypher:
MATCH (r:Recall {classification: 'Class I'})-[:RECALLED]->(:Product)<-[:OF_PRODUCT]-(:Package)-[:IS_DRUG]->(d:Drug {has_current_shortage: true})
WHERE r.initiation_date >= toString(date() - duration('P5Y'))
RETURN d.name AS drug, d.risk_tier AS risk_tier, count(DISTINCT r) AS class_1_recalls
ORDER BY class_1_recalls DESC
LIMIT 20"""

SYSTEM_PROMPT = f"""You translate questions about US drug shortages into ONE read-only Cypher query for Neo4j.

{SCHEMA}

Rules:
- Use only the node labels, relationships, and properties listed above.
- Return only the Cypher query: no explanation, no markdown, no code fences.
- When a question names a drug, match it by ingredient: (d:Drug)-[:HAS_INGREDIENT]->(i:Ingredient) WHERE toLower(i.name) CONTAINS '<ingredient>'.
- "Made only in <country>" means every known manufacturing site of the drug is in that country: collect countries per drug and compare to a one-item list.
- If the question asks about label content (storage, dosing, warnings, contraindications, indications), also return collect(DISTINCT l.spl_set_id) AS spl_set_ids via (l:Label)-[:DESCRIBES]->(:Product).
- Always end with a LIMIT of at most {MAX_ROWS}.
- If the question asks to change, add, or delete data, or cannot be answered from this graph, return exactly: {NO_QUERY}
- Return every property you filter on (for example risk_tier or alternative_status), so each row shows why it matches.

{EXAMPLES}"""


def clean(cypher):
    cypher = re.sub(r"```(?:cypher)?", "", cypher).strip()
    return cypher.rstrip(";").strip()


def validate(cypher):
    if cypher.strip() == NO_QUERY:
        raise NotAnswerable("This question can't be answered with a read-only query on the shortage graph.")
    if not READ_START.match(cypher):
        raise NotAnswerable(f"The model did not return a Cypher query:\n{cypher[:200]}")
    if FORBIDDEN.search(cypher):
        raise PermissionError(f"Rejected: query is not read-only.\n{cypher}")
    if not re.search(r"\bLIMIT\b", cypher, re.IGNORECASE):
        cypher = f"{cypher}\nLIMIT {MAX_ROWS}"
    return cypher


def generate(client, question, previous=None, error=None):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    if previous and error:
        messages += [
            {"role": "assistant", "content": previous},
            {"role": "user", "content": f"That query failed with this error:\n{error}\nReturn a corrected query only."},
        ]
    response = client.chat.completions.create(model=MODEL, temperature=0, messages=messages)
    usage = response.usage
    return clean(response.choices[0].message.content), usage.prompt_tokens, usage.completion_tokens


def run(question):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    cypher, p, c = generate(client, question)
    tokens["prompt_tokens"] += p
    tokens["completion_tokens"] += c

    for attempt in (1, 2):
        cypher = validate(cypher)
        try:
            with get_driver() as driver:
                records, _, _ = driver.execute_query(cypher, routing_=RoutingControl.READ)
            return {"question": question, "cypher": cypher, "rows": [r.data() for r in records],
                    "attempts": attempt, **tokens}
        except Exception as err:
            if attempt == 2:
                raise
            cypher, p, c = generate(client, question, previous=cypher, error=str(err))
            tokens["prompt_tokens"] += p
            tokens["completion_tokens"] += c


def main():
    question = " ".join(sys.argv[1:]) or "Which critical shortage drugs are made only in India?"
    try:
        result = run(question)
    except (PermissionError, NotAnswerable) as err:
        print(err)
        return
    print(f"Q: {question}\n\nCypher (attempts: {result['attempts']}):\n{result['cypher']}\n")
    print(f"{len(result['rows'])} rows")
    for row in result["rows"][:10]:
        print(" ", row)
    print(f"\n{MODEL} | {result['prompt_tokens']} in / {result['completion_tokens']} out tokens")


if __name__ == "__main__":
    main()