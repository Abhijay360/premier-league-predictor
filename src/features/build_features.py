from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from src.config import PREDICT_SEASON, get_paths
from src.dataio import load_raw_seasons, save_parquet
from src.features.team_state import TeamTracker
from src.ingest.fetch_squad_data import load_squad_data


@dataclass(frozen=True)
class FeatureConfig:
    form_window: int = 10
    baseline_window: int = 38


def _is_played_row(r: pd.Series) -> bool:
    if pd.isna(r.get("FTHG")) or pd.isna(r.get("FTAG")):
        return False
    ftr = r.get("FTR")
    if pd.isna(ftr):
        return False
    return str(ftr) in {"H", "D", "A"}


def build_rolling_team_table(matches: pd.DataFrame, cfg: FeatureConfig, predict_season: str = PREDICT_SEASON) -> pd.DataFrame:
    matches = matches.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
    squad_lookup = load_squad_data(predict_season)
    tracker = TeamTracker(form_window=cfg.form_window, baseline_window=cfg.baseline_window)

    rows = []
    current_season = None

    for _, r in matches.iterrows():
        home = str(r["HomeTeam"])
        away = str(r["AwayTeam"])
        played = _is_played_row(r)

        season = r.get("season")
        if season != current_season:
            tracker.snapshot_anchors()
            current_season = season

        is_predict = str(season) == str(predict_season)
        tracker.use_squad_features = is_predict
        tracker.squad_lookup = squad_lookup if is_predict else {}

        feat = {
            "Date": r["Date"],
            "season": r.get("season"),
            "HomeTeam": home,
            "AwayTeam": away,
            "FTHG": r["FTHG"],
            "FTAG": r["FTAG"],
            "FTR": r["FTR"],
            "home_cold_start": tracker.is_cold_start(home),
            "away_cold_start": tracker.is_cold_start(away),
        }
        feat.update(tracker.match_features(home, away))
        rows.append(feat)

        if played:
            tracker.update(home, away, int(r["FTHG"]), int(r["FTAG"]))

    feats = pd.DataFrame(rows)
    feats["played"] = feats.apply(_is_played_row, axis=1)
    feats["y_ftr"] = pd.NA
    feats.loc[feats["played"], "y_ftr"] = feats.loc[feats["played"], "FTR"].map({"H": 0, "D": 1, "A": 2})
    feats["home_win"] = pd.NA
    feats.loc[feats["played"], "home_win"] = (feats.loc[feats["played"], "FTR"] == "H").astype(int)
    feats["goal_diff"] = pd.NA
    feats.loc[feats["played"], "goal_diff"] = (
        feats.loc[feats["played"], "FTHG"].astype(int) - feats.loc[feats["played"], "FTAG"].astype(int)
    )
    return feats.reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build rolling-form features for PL matches.")
    p.add_argument("--seasons", nargs="+", required=True, help="Season codes like 2324.")
    p.add_argument("--window", type=int, default=10, help="Recent form window.")
    p.add_argument("--baseline", type=int, default=38, help="Baseline form window.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = FeatureConfig(form_window=args.window, baseline_window=args.baseline)
    matches = load_raw_seasons(args.seasons)
    feats = build_rolling_team_table(matches, cfg=cfg)

    paths = get_paths()
    out_all = paths.processed_dir / "match_features_all.parquet"
    out_played = paths.processed_dir / "match_features_played.parquet"
    out_upcoming = paths.processed_dir / "match_features_upcoming.parquet"

    save_parquet(feats, out_all)
    save_parquet(feats[feats["played"]].reset_index(drop=True), out_played)
    save_parquet(feats[~feats["played"]].reset_index(drop=True), out_upcoming)

    print(f"Wrote features (all): {out_all} ({len(feats)} rows)")
    print(f"Wrote features (played): {out_played} ({int(feats['played'].sum())} rows)")
    print(f"Wrote features (upcoming): {out_upcoming} ({int((~feats['played']).sum())} rows)")


if __name__ == "__main__":
    main()
