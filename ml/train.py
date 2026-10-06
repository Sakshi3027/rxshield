"""Train a shortage prediction model on rolling past cutoffs and evaluate on a held-out future window."""
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
ARTIFACTS = Path("ml/artifacts")
RESULTS = Path("ml/results")


def build_features(cutoff):
    subprocess.run(
        ["dbt", "run", "--select", "ml_product_features", "--vars", json.dumps({"ml_cutoff": cutoff})],
        cwd="dbt", check=True, stdout=subprocess.DEVNULL)
    features = pd.read_sql(text("select * from analytics.ml_product_features"), get_engine())
    return features.assign(cutoff=cutoff)


def precision_at_k(y, scores, k=100):
    top = np.argsort(-scores)[:k]
    return y[top].mean()


def evaluate(name, y, scores):
    return {"model": name,
            "pr_auc": round(average_precision_score(y, scores), 3),
            "roc_auc": round(roc_auc_score(y, scores), 3),
            "precision_at_100": round(precision_at_k(y, scores), 3)}


def main():
    train = pd.concat([build_features(c) for c in TRAIN_CUTOFFS], ignore_index=True)
    test = build_features(TEST_CUTOFF)

    print("Training windows:")
    print(train.groupby("cutoff")["label"].agg(positives="sum", products="count").to_string())
    print(f"Test window {TEST_CUTOFF}: {int(test['label'].sum())} positives of {len(test)} products\n")

    X_train, y_train = train[FEATURES].astype(float), train["label"].to_numpy()
    X_test, y_test = test[FEATURES].astype(float), test["label"].to_numpy()

    model = xgb.XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
        eval_metric="aucpr", random_state=42)
    model.fit(X_train, y_train)

    logistic = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    logistic.fit(X_train, y_train)

    results = [
        evaluate("random", y_test, np.random.default_rng(42).random(len(y_test))),
        evaluate("heuristic: maker prior shortages", y_test, X_test["labeler_prior_shortages"].to_numpy()),
        evaluate("logistic regression", y_test, logistic.predict_proba(X_test)[:, 1]),
        evaluate("xgboost", y_test, model.predict_proba(X_test)[:, 1]),
    ]
    print(pd.DataFrame(results).to_string(index=False))
    print(f"\nBase rate: {y_test.mean():.3f}")

    contributions = model.get_booster().predict(xgb.DMatrix(X_test), pred_contribs=True)[:, :-1]
    importance = pd.Series(np.abs(contributions).mean(axis=0), index=FEATURES).sort_values(ascending=False)
    print("\nMean absolute SHAP contribution:")
    print(importance.round(3).to_string())

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    model.save_model(ARTIFACTS / "shortage_model.json")
    (RESULTS / "evaluation.json").write_text(json.dumps(
        {"train_cutoffs": TRAIN_CUTOFFS, "test_cutoff": TEST_CUTOFF, "results": results,
         "shap_importance": importance.round(4).to_dict()}, indent=2))
    print(f"\nSaved model to {ARTIFACTS} and evaluation to {RESULTS}")


if __name__ == "__main__":
    main()