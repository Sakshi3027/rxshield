"""Generate synthetic private hospital documents, embed them, and store them with tenant and role access metadata."""
import random

import pandas as pd
from fastembed import TextEmbedding
from sqlalchemy import text

from ingestion.db import get_engine
from retrieval.embed_labels import MODEL_NAME, SEARCH_PATH, embed, to_vector

CLINICAL_ROLES = ["pharmacist", "clinician", "executive"]
PROCUREMENT_ROLES = ["procurement", "executive"]
CONSERVATION = [
    "Reserve remaining stock for ICU, operating room, and emergency department use.",
    "Dispense in unit doses from the smallest available vial size to reduce waste.",
    "Convert to the oral route when the patient can tolerate oral medication.",
    "Require pharmacist approval for every new order until supply recovers.",
    "Suspend use in elective procedures until supply recovers.",
]

SOURCE_SQL = """
    select t.tenant_id, t.name as tenant_name, f.drug_rxcui, f.drug_name,
           round(f.on_hand_units / f.avg_daily_units) as days_on_hand,
           c.supplier, c.unit_price, c.contract_end, r.alternative_status
    from tenancy.formulary f
    join tenancy.tenants t on t.tenant_id = f.tenant_id
    join tenancy.contracts c on c.tenant_id = f.tenant_id and c.drug_rxcui = f.drug_rxcui
    join analytics.mart_shortage_risk r on r.drug_rxcui = f.drug_rxcui
    where r.risk_tier in ('critical', 'high')
"""


def build_documents(rows):
    docs = []
    for row in rows.itertuples():
        rng = random.Random(f"{row.tenant_id}-{row.drug_rxcui}")
        substitution = (
            "Products of the same drug from another listed manufacturer may be substituted without prescriber contact."
            if row.alternative_status != "no_listed_alternative"
            else "No equivalent product from another manufacturer is listed, so prescribers must be contacted before any substitution."
        )
        docs.append({
            "chunk_id": f"{row.tenant_id}|protocol|{row.drug_rxcui}",
            "tenant_id": row.tenant_id, "doc_type": "protocol", "allowed_roles": CLINICAL_ROLES,
            "drug_rxcui": row.drug_rxcui, "title": f"Substitution protocol: {row.drug_name}",
            "content": (f"{row.tenant_name} Pharmacy and Therapeutics interim protocol for {row.drug_name}. "
                        f"Current supply covers about {int(row.days_on_hand)} days at the usual rate of use. "
                        f"{' '.join(rng.sample(CONSERVATION, 2))} {substitution} "
                        f"This protocol applies to all {row.tenant_name} facilities and is reviewed weekly."),
        })
        docs.append({
            "chunk_id": f"{row.tenant_id}|procurement|{row.drug_rxcui}",
            "tenant_id": row.tenant_id, "doc_type": "procurement_memo", "allowed_roles": PROCUREMENT_ROLES,
            "drug_rxcui": row.drug_rxcui, "title": f"Procurement memo: {row.drug_name}",
            "content": (f"{row.tenant_name} procurement memo for {row.drug_name}. Contracted supplier: {row.supplier} "
                        f"at ${row.unit_price} per unit through {row.contract_end}. Wholesaler allocation is limited to "
                        f"{rng.randint(20, 400)} units per week. Off-contract purchases are approved up to "
                        f"${rng.randint(5, 50) * 1000} per order with pharmacy director sign-off."),
        })
    return pd.DataFrame(docs)


def main():
    engine = get_engine()
    docs = build_documents(pd.read_sql(SOURCE_SQL, engine))
    print(f"Built {len(docs)} private documents")

    model = TextEmbedding(MODEL_NAME)
    vectors = embed(model, (docs["title"] + ": " + docs["content"]).tolist())
    docs["embedding"] = [to_vector(v) for v in vectors]

    with engine.begin() as conn:
        conn.execute(text(SEARCH_PATH))
        conn.execute(text("drop table if exists rag.tenant_chunks cascade"))
        conn.execute(text(f"""
            create table rag.tenant_chunks (
                chunk_id text primary key,
                tenant_id text not null references tenancy.tenants (tenant_id),
                doc_type text not null,
                allowed_roles text[] not null,
                drug_rxcui text,
                title text not null,
                content text not null,
                embedding vector({vectors.shape[1]}) not null
            )"""))
        conn.execute(text("alter table rag.tenant_chunks enable row level security"))
        conn.execute(text("""
            create policy tenant_role_read on rag.tenant_chunks for select
            using (tenant_id = tenancy.session_tenant() and tenancy.session_role() = any(allowed_roles))"""))
        conn.execute(text("grant select on rag.tenant_chunks to rxshield_app"))
        conn.execute(text("""
            insert into rag.tenant_chunks
                (chunk_id, tenant_id, doc_type, allowed_roles, drug_rxcui, title, content, embedding)
            values (:chunk_id, :tenant_id, :doc_type, :allowed_roles, :drug_rxcui, :title, :content,
                    cast(:embedding as vector))"""), docs.to_dict("records"))
        summary = conn.execute(text(
            "select tenant_id, doc_type, count(*) from rag.tenant_chunks group by 1, 2 order by 1, 2")).fetchall()
    for tenant_id, doc_type, n in summary:
        print(f"  {tenant_id:<11} {doc_type:<17} {n}")


if __name__ == "__main__":
    main()