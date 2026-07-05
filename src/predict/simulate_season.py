"""Simulate a season using the AdvancedFootballSimulator (Dixon-Coles + Monte Carlo)."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.config import PREDICT_SEASON, TRAIN_SEASONS, get_paths
from src.dataio import load_raw_seasons, save_parquet
from src.predict.advanced_simulator import AdvancedFootballSimulator
from src.predict.pl_simulator_seed import PremierLeagueSimulatorSeed
from src.predict.scoreline import modal_scoreline_conditional
from src.teams_meta import team_info, team_stadium


def _is_played(r: pd.Series) -> bool:
    return pd.notna(r.get("FTHG")) and pd.notna(r.get("FTAG")) and pd.notna(r.get("FTR"))


def _scoreline_from_rates(
    lam: float,
    mu: float,
    outcome: str,
) -> tuple[int, int]:
    return modal_scoreline_conditional(lam, mu, outcome)


def simulate_season_advanced(
    engine: AdvancedFootballSimulator,
    fixtures: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], list[tuple[str, str]]]:
    """
    Build per-fixture predictions and Monte Carlo standings.

    Returns (fixture_simulation_df, monte_carlo_standings_df).
    """
    fixtures = fixtures.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
    rows: list[dict] = []
    mc_fixtures: list[tuple[str, str]] = []

    for _, r in fixtures.iterrows():
        home = str(r["HomeTeam"])
        away = str(r["AwayTeam"])
        played = _is_played(r)

        lam, mu = engine.compute_dixon_coles_rates(home, away)
        p_h, p_d, p_a = engine.match_outcome_probabilities(home, away)
        pred_ftr = "H" if p_h >= p_d and p_h >= p_a else ("A" if p_a >= p_d else "D")
        pred_hg, pred_ag = _scoreline_from_rates(lam, mu, pred_ftr)

        if played:
            fthg, ftag = int(r["FTHG"]), int(r["FTAG"])
            actual_ftr = str(r["FTR"])
        else:
            fthg, ftag = pred_hg, pred_ag
            actual_ftr = None
            mc_fixtures.append((home, away))

        home_meta = team_info(home)
        date_str = pd.Timestamp(r["Date"]).strftime("%Y-%m-%d")
        rows.append({
            "match_id": f"{home}|{away}|{date_str}",
            "Date": r["Date"],
            "season": r.get("season"),
            "Round": r.get("Round"),
            "HomeTeam": home,
            "AwayTeam": away,
            "stadium": team_stadium(home),
            "stadium_image": home_meta["stadium_image"],
            "home_logo": home_meta["logo"],
            "away_logo": team_info(away)["logo"],
            "p_home": p_h,
            "p_draw": p_d,
            "p_away": p_a,
            "pred_ftr": pred_ftr,
            "pred_home_goals": pred_hg,
            "pred_away_goals": pred_ag,
            "pred_home_xg": lam,
            "pred_away_xg": mu,
            "pred_score": f"{pred_hg}–{pred_ag}",
            "dc_lambda": lam,
            "dc_mu": mu,
            "played": played,
            "FTHG": int(r["FTHG"]) if played else None,
            "FTAG": int(r["FTAG"]) if played else None,
            "FTR": actual_ftr,
        })

    sim_df = pd.DataFrame(rows)
    teams = sorted(set(sim_df["HomeTeam"]).union(set(sim_df["AwayTeam"])))
    if not mc_fixtures:
        mc_fixtures = list(zip(sim_df["HomeTeam"], sim_df["AwayTeam"]))

    return sim_df, teams, mc_fixtures


def run_simulation(
    season: str,
    train_seasons: list[str],
    simulations: int = 5_000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    engine = PremierLeagueSimulatorSeed(season, train_seasons).build()
    fixtures = load_raw_seasons([season])
    fixtures["season"] = season

    sim_df, teams, mc_fixtures = simulate_season_advanced(engine, fixtures)
    mc_table = engine.run_monte_carlo_season(teams, mc_fixtures, simulations=simulations)
    return sim_df, mc_table


def monte_carlo_to_standings(mc: pd.DataFrame) -> pd.DataFrame:
    """Convert Monte Carlo output to legacy standings schema for the web UI."""
    out = mc.copy()
    out["points"] = out["expected_points"].round().astype(int)
    out["gf"] = out["expected_gf"].astype(int)
    out["ga"] = out["expected_ga"].astype(int)
    out["gd"] = out["expected_gd"].astype(int)
    played = 38
    drawn_est = int(round(played * 0.23))
    out["played"] = played
    out["drawn"] = drawn_est
    out["won"] = ((out["points"] - drawn_est) / 3.0).round().astype(int)
    out["lost"] = (played - out["won"] - drawn_est).clip(lower=0).astype(int)
    return out[[
        "position", "team", "played", "won", "drawn", "lost",
        "gf", "ga", "gd", "points",
    ]]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dixon-Coles + Monte Carlo season simulation.")
    p.add_argument("--season", default=PREDICT_SEASON)
    p.add_argument("--simulations", type=int, default=5_000)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    paths = get_paths()
    sim, mc = run_simulation(args.season, TRAIN_SEASONS, simulations=args.simulations)

    out_preds = paths.processed_dir / "predictions_upcoming.parquet"
    out_sim = paths.processed_dir / "season_simulation.parquet"
    out_mc = paths.processed_dir / "monte_carlo_standings.parquet"

    upcoming = sim[~sim["played"]].copy()
    save_parquet(upcoming, out_preds)
    save_parquet(sim, out_sim)
    save_parquet(mc, out_mc)
    print(f"Engine: AdvancedFootballSimulator (Dixon-Coles + Monte Carlo)")
    print(f"Wrote simulated predictions: {out_preds} ({len(upcoming)} fixtures)")
    print(f"Wrote full simulation log: {out_sim} ({len(sim)} matches)")
    print(f"Wrote Monte Carlo standings: {out_mc} ({args.simulations:,} iterations)")
    print("\nTop 5 by expected points:")
    for _, r in mc.head(5).iterrows():
        print(
            f"  {int(r['position'])}. {r['team']}: "
            f"{r['expected_points']:.1f} pts "
            f"[{r['points_p95_lower']:.0f}–{r['points_p95_upper']:.0f}]"
        )


if __name__ == "__main__":
    main()
