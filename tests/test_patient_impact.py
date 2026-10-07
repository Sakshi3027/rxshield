import pandas as pd

from simulation.patient_impact import run_patient_impact, summarize_orders


def test_summary_counts_distinct_patients_and_icu():
    orders = pd.DataFrame({
        "drug_rxcui": ["A", "A", "A", "B"],
        "patient_ref": ["p1", "p1", "p2", "p1"],
        "care_unit": ["ICU", "ICU", "Oncology", "Med-Surg"],
    })
    summary = summarize_orders(orders).set_index("drug_rxcui")
    assert summary.loc["A", "active_orders"] == 3
    assert summary.loc["A", "patients"] == 2
    assert summary.loc["A", "icu_patients"] == 1
    assert summary.loc["A", "care_units"] == "ICU, Oncology"
    assert summary.loc["B", "icu_patients"] == 0


def test_empty_orders_give_empty_summary():
    empty = pd.DataFrame(columns=["drug_rxcui", "patient_ref", "care_unit"])
    assert summarize_orders(empty).empty


def test_pharmacist_gets_consistent_patient_impact():
    impact, total_patients = run_patient_impact("northshore-pharmacist", "country", "IND", 60)
    assert total_patients is not None
    assert (impact["patients"] <= impact["active_orders"]).all()
    assert (impact["icu_patients"] <= impact["patients"]).all()
    assert total_patients <= impact["patients"].sum()


def test_procurement_gets_no_patient_impact():
    impact, total_patients = run_patient_impact("northshore-procurement", "country", "IND", 60)
    assert total_patients is None
    assert "patients" not in impact.columns