"""Load Premier League historical archive from football-data CSVs."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.config import TRAIN_SEASONS, get_paths
from src.dataio import load_raw_seasons
from src.manager_adjustments import MANAGER_BOOST
from src.predict.backtest_calibration import (
    HistoricalSeasonData,
    SeasonRecord,
    TeamSeasonParameters,
    _double_round_robin,
    _table_from_results,
)


def _season_year(code: str) -> int:
    return 2000 + int(code[:2])


def _team_capability_from_results(
    team: str,
    prior_results: list[tuple[str, str, int, int]],
) -> float:
    """Derive 0–1 squad capability from historical goal difference per game."""
    if not prior_results:
        return 0.55
    gf = ga = n = 0
    for home, away, hg, ag in prior_results:
        if home == team:
            gf += hg
            ga += ag
            n += 1
        elif away == team:
            gf += ag
            ga += hg
            n += 1
    if n == 0:
        return 0.55
    gd_pg = (gf - ga) / n
    return float(np.clip(0.50 + gd_pg * 0.12, 0.25, 0.92))


def build_premier_league_historical_data(
    season_codes: list[str] | None = None,
    *,
    max_seasons: int | None = None,
) -> HistoricalSeasonData:
    """
    Build HistoricalSeasonData from downloaded PL CSV files.

    Team parameters for season Y use only results from seasons before Y.
    """
    codes = season_codes or TRAIN_SEASONS
    if max_seasons is not None:
        codes = codes[-max_seasons:]
    raw = load_raw_seasons(codes)
    archive = HistoricalSeasonData()
    all_prior_results: list[tuple[str, str, int, int]] = []

    for code in codes:
        year = _season_year(code)
        season_df = raw[raw["season"].astype(str) == code].dropna(subset=["FTHG", "FTAG"])
        if season_df.empty:
            continue

        teams = sorted(set(season_df["HomeTeam"]).union(set(season_df["AwayTeam"])))
        team_parameters: dict[str, TeamSeasonParameters] = {}
        for team in teams:
            cap = _team_capability_from_results(team, all_prior_results)
            mgr = float(np.clip(0.55 + MANAGER_BOOST.get(team, 0.0) * 1.8, 0.40, 0.96))
            pid = f"{team}|squad"
            team_parameters[team] = TeamSeasonParameters(
                team_id=team,
                squad_capability=cap,
                manager_skill=mgr,
                player_capabilities={pid: cap},
                player_health={pid: 1.0},
                starters=[pid],
            )

        fixtures = [
            (str(r.HomeTeam), str(r.AwayTeam))
            for r in season_df.sort_values("Date").itertuples()
        ]
        if not fixtures:
            fixtures = _double_round_robin(teams)

        results = [
            (str(r.HomeTeam), str(r.AwayTeam), int(r.FTHG), int(r.FTAG))
            for r in season_df.itertuples()
        ]
        actual_table = _table_from_results(teams, results)

        archive.seasons.append(SeasonRecord(
            year=year,
            team_parameters=team_parameters,
            fixtures=fixtures,
            match_results=results,
            actual_table=actual_table,
        ))
        all_prior_results.extend(results)

    return archive
