from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import get_paths


REQUIRED_COLUMNS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
OPTIONAL_COLUMNS = {"Date", "HomeTeam", "AwayTeam"}


def _parse_date_col(s: pd.Series) -> pd.Series:
    # football-data is usually dd/mm/yy or dd/mm/yyyy; be robust.
    dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return dt


def load_raw_season_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Some sources provide fixtures with missing goals/FTR for not-yet-played matches.
    missing_min = OPTIONAL_COLUMNS - set(df.columns)
    if missing_min:
        raise ValueError(f"Missing required columns in {path.name}: {sorted(missing_min)}")

    # If any of the "result" columns are missing, create them as empty.
    for col in ["FTHG", "FTAG", "FTR"]:
        if col not in df.columns:
            df[col] = pd.NA

    out = df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]].copy()
    out["Date"] = _parse_date_col(out["Date"])
    out = out.dropna(subset=["Date", "HomeTeam", "AwayTeam"])

    # Coerce scores to nullable ints; keep NA for upcoming fixtures.
    out["FTHG"] = pd.to_numeric(out["FTHG"], errors="coerce").astype("Int64")
    out["FTAG"] = pd.to_numeric(out["FTAG"], errors="coerce").astype("Int64")

    # FTR can be NA for upcoming fixtures.
    out["FTR"] = out["FTR"].astype("string")
    out = out.sort_values("Date").reset_index(drop=True)
    return out


def load_raw_seasons(seasons: Iterable[str]) -> pd.DataFrame:
    paths = get_paths()
    frames = []
    for s in seasons:
        p = paths.raw_dir / f"pl_{s}.csv"
        if not p.exists():
            raise FileNotFoundError(f"Raw CSV not found: {p}. Run ingest first.")
        df = load_raw_season_csv(p)
        df["season"] = s
        frames.append(df)
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)

