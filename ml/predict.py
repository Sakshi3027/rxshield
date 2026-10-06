"""Retrain the chosen model on all labeled windows, score products not yet in shortage, and explain each score."""
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from ingestion.db import get_engine
from ml.train import CLEAN_FEATURES, TEST_CUTOFF, TRAIN_CUTOFFS, build_features

ARTIFACTS = Path("ml/artifacts")
LABELED_CUTOFFS = TRAIN_CUTOFFS + [TEST_CUTOFF]
REASONS = {
    "recalls_before": "prior recalls on this product",
    "labeler_prior_shortages": "manufacturer has many past shortages",
    "labeler_recalls_before": "manufacturer recall history",
    "is_brand": "single-source brand product",
}


def explain(contributions):
    drivers = sorted(
        ((REASONS[f], v) for f, v in zip(CLEAN_FEATURES, contributions) if f in REASONS and v > 0),
        key=lambda pair: pair[1], reverse=True)
    return "; ".join(reason for reason, _ in drivers[:3]) or "no strong risk factors"


def main():
    train = pd.concat([build_features(c) for c in LABELED_CUTOFFS], ignore_index=True)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    model.fit(train[CLEAN_FEATURES].astype(float), train["label"])

    today = date.today().isoformat()
    current = build_features(today)
    build_features(TEST_CUTOFF)

    X = current[CLEAN_FEATURES].astype(float)
    current["risk_score"] = model.predict_proba(X)[:, 1].round(4)
    current["risk_percentile"] = (current["risk_score"].rank(pct=True) * 100).round(1)
    scaler = model.named_steps["standardscaler"]
    coefficients = model.named_steps["logisticregression"].coef_[0]
    current["top_reasons"] = [explain(row) for row in scaler.transform(X) * coefficients]

    predictions = current[["product", "labeler_code", "concept_rxcui", "concept_name",
                           "risk_score", "risk_percentile", "top_reasons"]].assign(scored_on=today)

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("create schema if not exists ml"))
        conn.execute(text("drop table if exists ml.shortage_predictions cascade"))
    predictions.to_sql("shortage_predictions", engine, schema="ml", index=False, if_exists="append")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACTS / "shortage_model.joblib")

    print(f"Trained on {len(train)} rows from {len(LABELED_CUTOFFS)} windows, scored {len(predictions)} products\n")
    top = predictions.sort_values("risk_score", ascending=False).head(12)
    for row in top.itertuples():
        print(f"{row.risk_percentile:>5}  {row.concept_name[:55]:<55}  labeler {row.labeler_code}  | {row.top_reasons}")


if __name__ == "__main__":
    main()