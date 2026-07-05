from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import streamlit as st

from src.config import get_paths
from src.dataio import load_parquet


st.set_page_config(page_title="Premier League Predictor", layout="wide")

paths = get_paths()
features_path = paths.processed_dir / "match_features_played.parquet"
preds_path = paths.processed_dir / "predictions_upcoming.parquet"
model_path = paths.models_dir / "pl_ftr_logreg.pkl"
report_path = paths.models_dir / "pl_ftr_logreg.report.json"

st.title("Premier League Predictor (Starter)")

colA, colB, colC = st.columns(3)
colA.metric("Features file", "Found" if features_path.exists() else "Missing")
colB.metric("Model file", "Found" if model_path.exists() else "Missing")
colC.metric("Report file", "Found" if report_path.exists() else "Missing")

if report_path.exists():
    report = json.loads(report_path.read_text())
    st.subheader("Training Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", report["n_rows"])
    c2.metric("Features", report["n_features"])
    c3.metric("CV Log Loss", f'{report["avg_log_loss"]:.4f}')
    c4.metric("CV Accuracy", f'{report["avg_accuracy"]:.3f}')

st.divider()

if not (features_path.exists() and model_path.exists()):
    st.info("Run: ingest → build_features → train_model → predict_season, then refresh this page.")
    st.stop()

df = load_parquet(features_path).sort_values("Date").reset_index(drop=True)
model = joblib.load(model_path)

st.subheader("Recent Backtest Slice (last N matches)")
n = st.slider("N matches", min_value=50, max_value=min(1000, len(df)), value=200, step=50)
recent = df.tail(n).copy()

feature_cols = [c for c in recent.columns if c in getattr(model, "feature_names_in_", [])]
if not feature_cols:
    # fallback to training default list embedded in report
    if report_path.exists():
        feature_cols = json.loads(report_path.read_text())["feature_cols"]
    else:
        st.error("Could not determine feature columns for model.")
        st.stop()

X = recent[feature_cols].astype(float)
proba = model.predict_proba(X)
pred = np.argmax(proba, axis=1)

recent["p_home"] = proba[:, 0]
recent["p_draw"] = proba[:, 1]
recent["p_away"] = proba[:, 2]
recent["pred_ftr"] = pd.Series(pred).map({0: "H", 1: "D", 2: "A"})

acc = float((recent["pred_ftr"] == recent["FTR"]).mean())
st.metric("Accuracy (slice)", f"{acc:.3f}")

show_cols = [
    "Date",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "FTR",
    "pred_ftr",
    "p_home",
    "p_draw",
    "p_away",
]
st.dataframe(
    recent[show_cols].sort_values("Date", ascending=False),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Upcoming Fixtures Predictions")
if not preds_path.exists():
    st.info("No upcoming predictions file found. Run: python3 -m src.predict.predict_season")
    st.stop()

preds = load_parquet(preds_path).sort_values("Date", ascending=True)
st.dataframe(
    preds,
    use_container_width=True,
    hide_index=True,
)

