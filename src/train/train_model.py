from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import get_paths
from src.dataio import load_parquet


FEATURE_COLS = [
    "home_avg_gf",
    "home_avg_ga",
    "home_avg_gd",
    "home_avg_pts",
    "home_win_rate",
    "away_avg_gf",
    "away_avg_ga",
    "away_avg_gd",
    "away_avg_pts",
    "away_win_rate",
    "home_elo",
    "away_elo",
    "elo_diff",
    "home_advantage",
    "home_prior_ppg",
    "away_prior_ppg",
    "home_squad_value_norm",
    "away_squad_value_norm",
    "home_net_spend_norm",
    "away_net_spend_norm",
    "home_squad_boost",
    "away_squad_boost",
]


@dataclass(frozen=True)
class TrainReport:
    n_rows: int
    n_features: int
    splits: int
    avg_log_loss: float
    avg_accuracy: float
    feature_cols: list[str]
    train_seasons: list[str]
    predict_season: str | None


def _ensure_cols(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")


def train_multiclass(
    df: pd.DataFrame,
    out_model: Path,
    out_report: Path,
    *,
    predict_season: str | None = None,
    last_n_seasons: int = 10,
) -> TrainReport:
    df = df.sort_values("Date").reset_index(drop=True)
    _ensure_cols(df, FEATURE_COLS + ["y_ftr"])

    # Keep only played rows with labels.
    df = df.dropna(subset=["y_ftr"]).copy()
    df["y_ftr"] = df["y_ftr"].astype(int)

    # Train on last N seasons, excluding the season we're predicting.
    if "season" in df.columns:
        seasons = sorted(df["season"].astype(str).unique().tolist())
        if predict_season is None:
            # If user doesn't specify, predict the latest season present and train on previous seasons.
            predict_season = seasons[-1] if seasons else None

        train_seasons = [s for s in seasons if s != predict_season][-last_n_seasons:]
        if train_seasons:
            df = df[df["season"].astype(str).isin(train_seasons)].copy()
    else:
        train_seasons = []

    X = df[FEATURE_COLS].astype(float)
    y = df["y_ftr"].astype(int)

    # Simple, strong baseline for tabular: scaled multinomial logistic regression.
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            ("clf", LogisticRegression(max_iter=5000)),
        ]
    )

    tss = TimeSeriesSplit(n_splits=5)
    losses: list[float] = []
    accs: list[float] = []

    for train_idx, test_idx in tss.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)
        pred = np.argmax(proba, axis=1)

        losses.append(float(log_loss(y_test, proba, labels=[0, 1, 2])))
        accs.append(float(accuracy_score(y_test, pred)))

    # Fit on full data at end.
    model.fit(X, y)
    out_model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_model)

    report = TrainReport(
        n_rows=int(len(df)),
        n_features=int(X.shape[1]),
        splits=int(tss.n_splits),
        avg_log_loss=float(np.mean(losses)),
        avg_accuracy=float(np.mean(accs)),
        feature_cols=list(FEATURE_COLS),
        train_seasons=list(train_seasons),
        predict_season=predict_season,
    )

    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(asdict(report), indent=2))
    return report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train baseline PL result model.")
    p.add_argument(
        "--features",
        default=None,
        help="Path to played features parquet (default: data/processed/match_features_played.parquet).",
    )
    p.add_argument(
        "--predict-season",
        default=None,
        help="Season code to hold out for prediction (e.g. 2526). If omitted, uses latest season in data.",
    )
    p.add_argument(
        "--last-n-seasons",
        type=int,
        default=10,
        help="How many past seasons to train on (excluding predict season).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    paths = get_paths()
    feat_path = (
        Path(args.features)
        if args.features
        else (paths.processed_dir / "match_features_played.parquet")
    )
    df = load_parquet(feat_path)

    model_path = paths.models_dir / "pl_ftr_logreg.pkl"
    report_path = paths.models_dir / "pl_ftr_logreg.report.json"
    report = train_multiclass(
        df,
        out_model=model_path,
        out_report=report_path,
        predict_season=args.predict_season,
        last_n_seasons=args.last_n_seasons,
    )

    print(f"Saved model: {model_path}")
    print(f"Saved report: {report_path}")
    print(f"CV avg logloss={report.avg_log_loss:.4f}  avg acc={report.avg_accuracy:.3f}")


if __name__ == "__main__":
    main()

