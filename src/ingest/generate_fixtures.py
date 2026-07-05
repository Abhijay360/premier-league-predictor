"""Generate a full-season fixture list when official CSV is not yet available."""

from __future__ import annotations

import argparse
import itertools
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.config import get_paths


def round_robin(teams: list[str]) -> list[tuple[str, str]]:
    """Single round-robin pairings (home/away alternating per week)."""
    n = len(teams)
    if n % 2:
        teams = teams + ["BYE"]
        n += 1
    rotation = teams[:]
    rounds: list[tuple[str, str]] = []
    for _ in range(n - 1):
        for i in range(n // 2):
            home = rotation[i]
            away = rotation[n - 1 - i]
            if home != "BYE" and away != "BYE":
                rounds.append((home, away))
        rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]
    return rounds


def full_season_fixtures(teams: list[str]) -> list[tuple[str, str, str]]:
    """First leg + return leg."""
    first = round_robin(teams)
    second = [(away, home) for home, away in first]
    start = datetime(2026, 8, 15)
    rows: list[tuple[str, str, str]] = []
    all_legs = first + second
    matchday = 0
    per_day = len(teams) // 2
    for i in range(0, len(all_legs), per_day):
        matchday += 1
        day = start + timedelta(days=7 * (matchday - 1))
        date_str = day.strftime("%d/%m/%Y")
        for home, away in all_legs[i : i + per_day]:
            rows.append((date_str, home, away))
    return rows


def teams_from_previous_season(season: str) -> list[str]:
    paths = get_paths()
    prev_code = str(int(season) - 101).zfill(4)
    prev = paths.raw_dir / f"pl_{prev_code}.csv"
    if not prev.exists():
        raise FileNotFoundError(f"Need {prev} to infer teams.")
    df = pd.read_csv(prev)
    return sorted(set(df["HomeTeam"].astype(str)) | set(df["AwayTeam"].astype(str)))


def write_fixtures_csv(season: str, teams: list[str] | None = None) -> Path:
    if teams is None:
        # Infer from previous season code (e.g. 2627 -> 2526)
        prev = str(int(season[:2])) + season[2:]
        teams = teams_from_previous_season(prev)

    rows = full_season_fixtures(teams)
    df = pd.DataFrame(rows, columns=["Date", "HomeTeam", "AwayTeam"])
    df["Div"] = "E0"
    df["FTHG"] = pd.NA
    df["FTAG"] = pd.NA
    df["FTR"] = pd.NA

    paths = get_paths()
    out = paths.raw_dir / f"pl_{season}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate fixture CSV for upcoming season.")
    p.add_argument("--season", required=True, help="Season code e.g. 2627")
    p.add_argument("--from-season", default=None, help="Copy teams from this season CSV.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    teams = teams_from_previous_season(args.from_season) if args.from_season else None
    path = write_fixtures_csv(args.season, teams=teams)
    print(f"Wrote {len(pd.read_csv(path))} fixtures to {path}")


if __name__ == "__main__":
    main()
