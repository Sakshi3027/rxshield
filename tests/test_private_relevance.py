from retrieval.private_search import query_private
from retrieval.tenant_rag import graph_evidence
from tenancy.db import user_session


def documents_for(question):
    rxcuis = sorted({row["rxcui"] for row in graph_evidence(question)["rows"] if row.get("rxcui")})
    with user_session("northshore-pharmacist") as conn:
        return query_private(conn, question, 4, rxcuis=rxcuis)


def test_documents_are_limited_to_the_drugs_asked_about():
    documents = documents_for("How many days of pentostatin do we have?")
    assert documents
    assert all("pentostatin" in d["title"].lower() for d in documents)


def test_drug_without_a_protocol_gets_no_documents():
    assert documents_for("How many days of heparin do we have?") == []