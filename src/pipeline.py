"""One-command pipeline: download → features → train → predict."""

from __future__ import annotations

import argparse
import subprocess
import sys

from src.config import PREDICT_SEASON, TRAIN_SEASONS


def _run(cmd: list[str]) -> None:
    print(f"\n>>> {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


def run_pipeline(
    train_seasons: list[str] | None = None,
    predict_season: str = PREDICT_SEASON,
    last_n_seasons: int = 10,
) -> None:
    train_seasons = train_seasons or TRAIN_SEASONS
    py = sys.executable
    all_seasons = [*train_seasons, predict_season]

    # 1) Historical results (last 10 seasons) from football-data.co.uk
    _run([py, "-m", "src.ingest.download_csv", "--seasons", *train_seasons])
    _run([py, "-m", "src.validate_training_data", "--predict-season", predict_season])

    # 2) Squad values and transfer spend (Transfermarkt)
    _run([py, "-m", "src.ingest.fetch_squad_data", "--season", predict_season])
    _run([py, "scripts/download_stadiums.py"])

    # 3) Official fixture list for the season we're predicting
    _run([py, "-m", "src.ingest.download_official_fixtures", "--season", predict_season])

    # 3) If football-data publishes results for predict season, merge them in
    _run([py, "-m", "src.ingest.merge_season_results", "--season", predict_season])

    _run([py, "-m", "src.features.build_features", "--seasons", *all_seasons])
    # Legacy sklearn model kept for /api/accuracy endpoints only
    _run([
        py, "-m", "src.train.train_model",
        "--predict-season", predict_season,
        "--last-n-seasons", str(last_n_seasons),
    ])
    _run([py, "-m", "src.predict.simulate_season", "--season", predict_season, "--simulations", "5000"])
    print("\nPipeline complete.")


def main() -> None:
    p = argparse.ArgumentParser(description="Run full PL prediction pipeline.")
    p.add_argument("--train-seasons", nargs="+", default=None)
    p.add_argument("--predict-season", default=PREDICT_SEASON)
    p.add_argument("--last-n-seasons", type=int, default=10)
    args = p.parse_args()
    run_pipeline(args.train_seasons, args.predict_season, args.last_n_seasons)


if __name__ == "__main__":
    main()
