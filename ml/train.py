"""Shortage prediction: ablation over training windows and feature sets, evaluated on a held-out future window."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from ingestion.db import get_engine

load_dotenv(".env")

TRAIN_CUTOFFS = ["2022-10-01", "2023-10-01", "2024-10-01"]
TEST_CUTOFF = "2025-10-01"
FEATURES = [
    "is_brand", "is_injectable", "recalls_before", "class_1_recalls_before", "recalls_last_2y",
    "quality_recalls_before", "labeler_recalls_before", "labeler_prior_shortages",
    "family_prior_shortages", "labelers_for_drug",
]
SUSPECT = {"labelers_for_drug", "family_prior_shortages"}
CLEAN_FEATURES = [f for f in FEATURES if f not in SUSPECT]
EXPERIMENTS = [
    ("A: all windows, all features", TRAIN_CUTOFFS, FEATURES),
    ("B: all windows, clean features", TRAIN_CUTOFFS, CLEAN_FEATURES),
    ("C: 2022 window, clean features", ["2022-10-01"], CLEAN_FEATURES),
]
RESULTS = Path("ml/results")


def build_features(cutoff):
    subprocess.run(
        ["dbt", "run", "--select", "ml_product_features", "--vars", json.dumps({"ml_cutoff": cutoff})],
        cwd="dbt", check=True, stdout=subprocess.DEVNULL)
    features = pd.read_sql(text("select * from analytics.ml_product_features"), get_engine())
    return features.assign(cutoff=cutoff)


def precision_at_k(y, scores, k=100):
    return y[np.argsort(-scores)[:k]].mean()


def evaluate(experiment, model_name, y, scores):
    return {"experiment": experiment, "model": model_name,
            "pr_auc": round(average_precision_score(y, scores), 3),
            "roc_auc": round(roc_auc_score(y, scores), 3),
            "precision_at_100": round(precision_at_k(y, scores), 3)}


def fit_models(train, features):
    X, y = train[features].astype(float), train["label"].to_numpy()
    booster = xgb.XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y == 0).sum() / max((y == 1).sum(), 1),
        eval_metric="aucpr", random_state=42)
    booster.fit(X, y)
    logistic = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    logistic.fit(X, y)
    return booster, logistic


def main():
    windows = {cutoff: build_features(cutoff) for cutoff in TRAIN_CUTOFFS}
    test = build_features(TEST_CUTOFF)
    y_test = test["label"].to_numpy()

    rows = [
        evaluate("baseline", "random", y_test, np.random.default_rng(42).random(len(y_test))),
        evaluate("baseline", "heuristic: maker prior shortages", y_test,
                 test["labeler_prior_shortages"].to_numpy().astype(float)),
    ]
    coefficients = {}
    for name, cutoffs, features in EXPERIMENTS:
        train = pd.concat([windows[c] for c in cutoffs], ignore_index=True)
        booster, logistic = fit_models(train, features)
        X_test = test[features].astype(float)
        rows.append(evaluate(name, "logistic regression", y_test, logistic.predict_proba(X_test)[:, 1]))
        rows.append(evaluate(name, "xgboost", y_test, booster.predict_proba(X_test)[:, 1]))
        coefficients[name] = dict(zip(features, logistic.named_steps["logisticregression"].coef_[0].round(3)))

    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    print(f"\nBase rate: {y_test.mean():.3f}")

    print("\nLogistic regression coefficients, experiment B (standardized features):")
    print(pd.Series(coefficients["B: all windows, clean features"]).sort_values(ascending=False).to_string())

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "ablation.json").write_text(json.dumps(
        {"test_cutoff": TEST_CUTOFF, "results": rows,
         "logistic_coefficients": {k: {f: float(v) for f, v in c.items()} for k, c in coefficients.items()}},
        indent=2))
    print(f"\nSaved ablation results to {RESULTS / 'ablation.json'}")


if __name__ == "__main__":
    main()