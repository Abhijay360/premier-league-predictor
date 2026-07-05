"""Merge match results from football-data into the official fixture CSV."""

from __future__ import annotations

import argparse
from io import StringIO

import pandas as pd
import requests

from src.config import LEAGUE_CODE, get_paths
from src.dataio import load_raw_season_csv
from src.ingest.download_csv import season_to_url


def _try_download_results(season: str) -> pd.DataFrame | None:
    url = season_to_url(season)
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return None
        df = pd.read_csv(StringIO(r.text))
        if "FTHG" not in df.columns:
            return None
        played = df.dropna(subset=["FTHG", "FTAG", "FTR"])
        if len(played) == 0:
            return None
        return played
    except Exception:
        return None


def merge_season_results(season: str) -> None:
    paths = get_paths()
    fixture_path = paths.raw_dir / f"pl_{season}.csv"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture file missing: {fixture_path}")

    fixtures = pd.read_csv(fixture_path)
    results = _try_download_results(season)

    if results is None:
        print(f"No football-data results yet for {season}; keeping official fixtures only.")
        return

    # Merge on home/away teams (dates can shift with TV rescheduling).
    key_cols = ["HomeTeam", "AwayTeam"]
    merged = fixtures.drop(columns=["FTHG", "FTAG", "FTR"], errors="ignore").merge(
        results[key_cols + ["FTHG", "FTAG", "FTR"]],
        on=key_cols,
        how="left",
        suffixes=("", "_fd"),
    )
    for col in ["FTHG", "FTAG", "FTR"]:
        if f"{col}_fd" in merged.columns:
            merged[col] = merged[f"{col}_fd"].combine_first(merged.get(col))
            merged.drop(columns=[f"{col}_fd"], inplace=True)

    merged.to_csv(fixture_path, index=False)
    n_played = merged["FTR"].notna().sum()
    print(f"Merged results into {fixture_path}: {n_played}/{len(merged)} matches have scores.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge football-data results into fixture CSV.")
    p.add_argument("--season", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    merge_season_results(args.season)


if __name__ == "__main__":
    main()
