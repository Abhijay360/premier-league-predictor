from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.config import get_paths
from src.dataio import load_parquet, save_parquet
from src.train.train_model import FEATURE_COLS


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Predict upcoming fixtures for a season.")
    p.add_argument(
        "--upcoming-features",
        default=None,
        help="Path to upcoming features parquet (default: data/processed/match_features_upcoming.parquet).",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Path to trained model (default: data/models/pl_ftr_logreg.pkl).",
    )
    p.add_argument(
        "--season",
        default=None,
        help="Season code to filter predictions to (e.g. 2526). If omitted, predicts all upcoming rows.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    paths = get_paths()

    feat_path = (
        Path(args.upcoming_features)
        if args.upcoming_features
        else (paths.processed_dir / "match_features_upcoming.parquet")
    )
    model_path = Path(args.model) if args.model else (paths.models_dir / "pl_ftr_logreg.pkl")

    upcoming = load_parquet(feat_path).copy()
    if args.season is not None and "season" in upcoming.columns:
        upcoming = upcoming[upcoming["season"].astype(str) == str(args.season)].copy()

    if len(upcoming) == 0:
        print("No upcoming fixtures found in features file.")
        return

    model = joblib.load(model_path)

    X = upcoming[FEATURE_COLS].astype(float)
    proba = model.predict_proba(X)
    pred = np.argmax(proba, axis=1)

    out = upcoming[["Date", "season", "HomeTeam", "AwayTeam"]].copy()
    out["p_home"] = proba[:, 0]
    out["p_draw"] = proba[:, 1]
    out["p_away"] = proba[:, 2]
    out["pred_ftr"] = pd.Series(pred).map({0: "H", 1: "D", 2: "A"})
    out = out.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)

    out_path = paths.processed_dir / "predictions_upcoming.parquet"
    save_parquet(out, out_path)
    print(f"Wrote predictions: {out_path} ({len(out)} fixtures)")


if __name__ == "__main__":
    main()

