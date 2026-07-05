"""Validate that training data covers the configured seasons."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from src.config import PREDICT_SEASON, TRAIN_SEASONS, get_paths
from src.dataio import load_raw_season_csv


@dataclass
class SeasonReport:
    season: str
    label: str
    path: str
    exists: bool
    matches: int
    date_min: str | None
    date_max: str | None
    teams: int


def season_label(code: str) -> str:
    y1, y2 = int(code[:2]), int(code[2:])
    return f"20{y1}-{y2}"


def validate_training_data(
    train_seasons: list[str] | None = None,
    predict_season: str = PREDICT_SEASON,
) -> dict:
    train_seasons = train_seasons or TRAIN_SEASONS
    paths = get_paths()
    reports: list[SeasonReport] = []

    for s in train_seasons:
        p = paths.raw_dir / f"pl_{s}.csv"
        if not p.exists():
            reports.append(SeasonReport(s, season_label(s), str(p), False, 0, None, None, 0))
            continue
        df = load_raw_season_csv(p)
        played = df.dropna(subset=["FTHG", "FTAG", "FTR"])
        teams = len(set(played["HomeTeam"]) | set(played["AwayTeam"]))
        reports.append(SeasonReport(
            season=s,
            label=season_label(s),
            path=str(p),
            exists=True,
            matches=int(len(played)),
            date_min=str(played["Date"].min().date()) if len(played) else None,
            date_max=str(played["Date"].max().date()) if len(played) else None,
            teams=teams,
        ))

    total_matches = sum(r.matches for r in reports)
    missing = [r.season for r in reports if not r.exists]
    short = [r.season for r in reports if r.exists and r.matches < 300]

    manifest = {
        "train_seasons": train_seasons,
        "predict_season": predict_season,
        "train_season_count": len(train_seasons),
        "total_training_matches": total_matches,
        "missing_seasons": missing,
        "seasons_with_few_matches": short,
        "valid": len(missing) == 0 and len(train_seasons) == 10 and total_matches >= 3000,
        "seasons": [asdict(r) for r in reports],
        "data_source": "https://www.football-data.co.uk/englandm.php",
        "notes": (
            "Training uses completed match results only (goals + H/D/A). "
            "The model does not ingest player signings or squad lists."
        ),
    }

    out = paths.processed_dir / "training_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    return manifest


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate 10-season training data.")
    p.add_argument("--predict-season", default=PREDICT_SEASON)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    m = validate_training_data(predict_season=args.predict_season)
    print(json.dumps(m, indent=2))
    if not m["valid"]:
        raise SystemExit("Training data validation failed.")
    print(f"\nOK: {m['train_season_count']} seasons, {m['total_training_matches']} matches")


if __name__ == "__main__":
    main()
