"""Permission-aware semantic answer cache: entity signature plus similarity, scoped by tenant and role."""
import re
import json
from functools import lru_cache

from sqlalchemy import text

from retrieval.embed_labels import SEARCH_PATH
from retrieval.tenant_rag import answer_for_user
from retrieval.vector_search import embed_query
from tenancy.audit import log_access
from tenancy.db import get_app_engine, user_session

SIMILARITY_THRESHOLD = 0.90
MAX_AGE_HOURS = 24
TIERS = {
    r"\bcritical\b": "tier:critical",
    r"\bhigh[\s-]risk\b": "tier:high",
    r"\belevated\b": "tier:elevated",
}
INTENTS = {
    r"\bstor(e|ed|age|ing)\b": "storage",
    r"\bcontraindicat": "contraindications",
    r"\bboxed warning": "boxed_warning",
    r"\bdos(e|es|ing|age)\b": "dosing",
    r"\brecall": "recalls",
    r"\b(alternativ|substitut|replace)": "alternatives",
    r"\b(manufactur|made\b|plant|facilit|site)": "manufacturing",
    r"\bcompan": "company",
    r"\bcountr": "country",
    r"\b(days|supply|stock|inventory|on hand)\b": "inventory",
    r"\b(price|cost|contract)": "pricing",
    r"\bprotocol": "protocol",
    r"\bindicat|\bused for\b": "indications",
    r"\bhow many\b": "count",
    r"\bshortage|\bin short supply": "shortage_status",
}


@lru_cache(maxsize=1)
def vocabulary():
    with get_app_engine().connect() as conn:
        ingredients = conn.execute(text(
            "select distinct lower(ingredient_name) from analytics.stg_drug_ingredients")).scalars().all()
        brands = conn.execute(text(r"""
            select distinct lower(substring(e.equivalent_name from '\[([^\]]+)\]')),
                            lower(i.ingredient_name)
            from analytics.stg_drug_equivalents e
            join analytics.stg_drug_ingredients i on i.drug_rxcui = e.drug_rxcui
            where e.equivalent_name like '%[%'""")).fetchall()
        countries = conn.execute(text(
            "select distinct lower(country), country_code from analytics.stg_facilities")).fetchall()

    terms = {name: {f"drug:{name}"} for name in ingredients}
    for brand, ingredient in brands:
        if brand:
            terms.setdefault(brand, set()).add(f"drug:{ingredient}")
    for name, code in countries:
        if name:
            terms.setdefault(name, set()).add(f"country:{code}")
    terms.setdefault("usa", set()).add("country:USA")

    alternatives = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return terms, re.compile(rf"\b({alternatives})\b")


def signature(question):
    terms, pattern = vocabulary()
    lowered = question.lower()
    tokens = set()
    for match in pattern.finditer(lowered):
        tokens |= terms[match.group(1)]
    for regex, token in {**TIERS, **INTENTS}.items():
        if re.search(regex, lowered):
            tokens.add(token)
    return "|".join(sorted(tokens))


def current_data_version(conn):
    return conn.execute(text("select max(snapshot_ts) from analytics.stg_shortage_events")).scalar()


def lookup(conn, sig, query_vector, version):
    conn.execute(text(SEARCH_PATH))
    row = conn.execute(text("""
        select cache_id, question, answer, 1 - (embedding <=> cast(:q as vector)) as similarity
        from rag.answer_cache
        where signature = :sig and data_version = :v
          and created_at > now() - make_interval(hours => :h)
        order by embedding <=> cast(:q as vector)
        limit 1"""), {"q": query_vector, "sig": sig, "v": version, "h": MAX_AGE_HOURS}).mappings().one_or_none()
    if row and row["similarity"] >= SIMILARITY_THRESHOLD:
        return dict(row)
    return None


def store(conn, question, sig, query_vector, payload, version):
    conn.execute(text(SEARCH_PATH))
    conn.execute(text("""
        insert into rag.answer_cache
            (scope_tenant, scope_role, signature, question, embedding, answer, data_version)
        values (tenancy.session_tenant(), tenancy.session_role(), :sig, :question,
                cast(:q as vector), cast(:answer as jsonb), :v)"""),
        {"sig": sig, "question": question, "q": query_vector, "answer": json.dumps(payload, default=str), "v": version})


def cached_answer_for_user(user_id, question):
    sig = signature(question)
    if not sig:
        return {**answer_for_user(user_id, question), "cache": "skipped"}

    query_vector = embed_query(question)
    with user_session(user_id) as conn:
        version = current_data_version(conn)
        hit = lookup(conn, sig, query_vector, version)
        if hit:
            log_access(conn, "cache_hit", question, {
                "cache_id": hit["cache_id"], "matched_question": hit["question"],
                "similarity": round(float(hit["similarity"]), 3)})
            return {**hit["answer"], "cache": "hit", "similarity": round(float(hit["similarity"]), 3),
                    "prompt_tokens": 0, "completion_tokens": 0}

    result = answer_for_user(user_id, question)
    payload = {key: result[key] for key in ("answer", "role", "tenant_name", "display_name")}
    with user_session(user_id) as conn:
        store(conn, question, sig, query_vector, payload, version)
    return {**result, "cache": "miss"}