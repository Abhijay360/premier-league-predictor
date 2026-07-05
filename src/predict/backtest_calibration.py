"""
10-Year Algorithmic Backtesting & Self-Calibration Engine.

Ingests historical season data, runs Dixon-Coles / Monte Carlo backtests,
and auto-tunes simulator hyperparameters via scipy.optimize.

Dependencies: numpy, pandas, scipy only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.predict.advanced_simulator import AdvancedFootballSimulator

CALIBRATED_PARAMS_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "calibrated_params.json"

# Tunable parameter bounds: [time_decay, home_adv, chemistry, h2h]
PARAM_BOUNDS = [
    (0.001, 1.50),   # time_decay_factor → h2h_decay
    (0.05, 0.60),    # home_advantage_baseline
    (0.05, 1.00),    # chemistry_weight
    (0.01, 0.35),    # h2h_weight → h2h_coef
]

INITIAL_PARAMS = np.array([0.001, 0.25, 0.20, 0.05], dtype=float)
POSITION_PENALTY_WEIGHT = 1.75  # secondary loss on table-rank displacement


@dataclass
class TeamSeasonParameters:
    """Per-team baseline state for a single historical season."""
    team_id: str
    squad_capability: float
    manager_skill: float
    player_capabilities: dict[str, float] = field(default_factory=dict)
    player_health: dict[str, float] = field(default_factory=dict)
    starters: list[str] = field(default_factory=list)


@dataclass
class SeasonRecord:
    """All data required to simulate and evaluate one historical season."""
    year: int
    team_parameters: dict[str, TeamSeasonParameters]
    fixtures: list[tuple[str, str]]
    match_results: list[tuple[str, str, int, int]]  # home, away, hg, ag
    actual_table: pd.DataFrame  # team, points, position [, gf, ga]


@dataclass
class HistoricalSeasonData:
    """Container for 10-year (or arbitrary) historical league archive."""

    seasons: list[SeasonRecord] = field(default_factory=list)

    def years(self) -> list[int]:
        return [s.year for s in self.seasons]

    def get(self, year: int) -> SeasonRecord | None:
        for s in self.seasons:
            if s.year == year:
                return s
        return None

    def prior_seasons(self, year: int) -> list[SeasonRecord]:
        return [s for s in self.seasons if s.year < year]


# ---------------------------------------------------------------------------
# Layer 1 — simulator seeding from historical records
# ---------------------------------------------------------------------------

def _double_round_robin(teams: list[str]) -> list[tuple[str, str]]:
    fixtures: list[tuple[str, str]] = []
    for i, home in enumerate(teams):
        for j, away in enumerate(teams):
            if i != j:
                fixtures.append((home, away))
    return fixtures


def _table_from_results(
    teams: list[str],
    results: list[tuple[str, str, int, int]],
) -> pd.DataFrame:
    pts: dict[str, int] = {t: 0 for t in teams}
    gf: dict[str, int] = {t: 0 for t in teams}
    ga: dict[str, int] = {t: 0 for t in teams}
    for home, away, hg, ag in results:
        gf[home] += hg
        ga[home] += ag
        gf[away] += ag
        ga[away] += hg
        if hg > ag:
            pts[home] += 3
        elif hg < ag:
            pts[away] += 3
        else:
            pts[home] += 1
            pts[away] += 1
    rows = [
        {
            "team": t,
            "points": pts[t],
            "gf": gf[t],
            "ga": ga[t],
            "gd": gf[t] - ga[t],
        }
        for t in teams
    ]
    df = pd.DataFrame(rows).sort_values(["points", "gd", "gf"], ascending=False).reset_index(drop=True)
    df.insert(0, "position", np.arange(1, len(df) + 1))
    return df


def seed_simulator_from_season(
    season: SeasonRecord,
    prior_seasons: list[SeasonRecord],
    params: np.ndarray | None = None,
) -> AdvancedFootballSimulator:
    """Build a simulator for one season using only information available pre-season."""
    eng = AdvancedFootballSimulator()
    if params is not None:
        eng.apply_params(params)

    for tp in season.team_parameters.values():
        mgr_id = f"mgr|{tp.team_id}|{season.year}"
        eng.register_manager(mgr_id, tp.manager_skill)

        roster: list[str] = []
        starters = tp.starters or list(tp.player_capabilities.keys())[:5]
        for pid, cap in tp.player_capabilities.items():
            eng.register_player(pid, cap)
            eng.player_attack_weight[pid] = 1.0
            eng.player_defence_weight[pid] = 1.0
            roster.append(pid)
            health = tp.player_health.get(pid, 1.0)
            eng.set_player_health(pid, health)

        if not roster:
            pid = f"{tp.team_id}|core"
            eng.register_player(pid, tp.squad_capability)
            eng.set_player_health(pid, 1.0)
            roster = [pid]
            starters = [pid]

        eng.register_team(tp.team_id, roster, mgr_id, starters=starters)
        eng.team_squad_boost[tp.team_id] = tp.squad_capability

    ref_year = float(season.year)
    for prev in prior_seasons:
        for home, away, hg, ag in prev.match_results:
            age = max(0.0, ref_year - prev.year)
            eng.register_h2h_match(home, away, hg, ag, age_years=age)

    return eng


# ---------------------------------------------------------------------------
# Layer 2 — evaluation metric
# ---------------------------------------------------------------------------

def calculate_season_rmse(
    predicted_df: pd.DataFrame,
    actual_table: pd.DataFrame,
    *,
    position_penalty: float = POSITION_PENALTY_WEIGHT,
) -> dict[str, float]:
    """
    RMSE on expected points plus position-displacement penalty.

    Returns dict with rmse, position_error, combined_loss.
    """
    actual_pts = actual_table.set_index("team")["points"].to_dict()
    actual_pos = actual_table.set_index("team")["position"].to_dict()
    pred_pts = predicted_df.set_index("team")["expected_points"].to_dict()
    pred_pos = predicted_df.set_index("team")["position"].to_dict()

    teams = sorted(set(actual_pts) & set(pred_pts))
    if not teams:
        return {"rmse": float("inf"), "position_error": float("inf"), "combined_loss": float("inf")}

    pt_errors = np.array([pred_pts[t] - actual_pts[t] for t in teams], dtype=float)
    rmse = float(np.sqrt(np.mean(pt_errors ** 2)))

    pos_errors = np.array([abs(pred_pos[t] - actual_pos[t]) for t in teams], dtype=float)
    position_error = float(np.mean(pos_errors))
    combined_loss = rmse + position_penalty * position_error

    return {
        "rmse": rmse,
        "position_error": position_error,
        "combined_loss": combined_loss,
    }


# ---------------------------------------------------------------------------
# Layer 3 — 10-year backtesting loop
# ---------------------------------------------------------------------------

def run_10_year_backtest(
    params: np.ndarray | list[float],
    historical_data: HistoricalSeasonData,
    simulations: int = 500,
    seed: int = 42,
    verbose: bool = False,
    *,
    analytical: bool = False,
) -> tuple[float, list[dict[str, Any]]]:
    """
    Chronological backtest across all seasons.

    When analytical=True (or simulations=0), uses Poisson expected points
    instead of Monte Carlo — much faster for calibration loops.

    Returns (mean_combined_loss, per-season metrics list).
    """
    params = np.asarray(params, dtype=float)
    season_metrics: list[dict[str, Any]] = []
    losses: list[float] = []
    use_analytical = analytical or simulations <= 0

    for season in historical_data.seasons:
        prior = historical_data.prior_seasons(season.year)
        eng = seed_simulator_from_season(season, prior, params=params)
        teams = sorted(season.team_parameters.keys())
        if use_analytical:
            pred = eng.predict_season_analytical(teams, season.fixtures)
        else:
            pred = eng.run_monte_carlo_season(
                teams,
                season.fixtures,
                simulations=simulations,
                seed=seed + season.year,
            )
        metrics = calculate_season_rmse(pred, season.actual_table)
        metrics["year"] = season.year
        metrics["predicted"] = pred
        season_metrics.append(metrics)
        losses.append(metrics["combined_loss"])
        if verbose:
            print(
                f"  {season.year}: RMSE={metrics['rmse']:.2f}  "
                f"PosErr={metrics['position_error']:.2f}  "
                f"Combined={metrics['combined_loss']:.2f}"
            )

    mean_loss = float(np.mean(losses)) if losses else float("inf")
    return mean_loss, season_metrics


# ---------------------------------------------------------------------------
# Layer 4 — self-calibration
# ---------------------------------------------------------------------------

def calibrate_model(
    historical_data: HistoricalSeasonData,
    *,
    initial_params: np.ndarray | None = None,
    simulations: int = 0,
    method: str = "L-BFGS-B",
    maxiter: int = 25,
) -> tuple[np.ndarray, Any]:
    """
    Find hyperparameters that minimise mean 10-year combined loss.

    Default simulations=0 uses fast analytical expected points during search;
    verify with simulations=500 after calibration.
    """
    x0 = np.asarray(initial_params if initial_params is not None else INITIAL_PARAMS, dtype=float)
    eval_count = [0]
    best = [float("inf")]

    def objective(x: np.ndarray) -> float:
        eval_count[0] += 1
        loss, _ = run_10_year_backtest(
            x, historical_data,
            simulations=simulations,
            analytical=(simulations <= 0),
            seed=100 + eval_count[0],
        )
        if loss < best[0]:
            best[0] = loss
        if eval_count[0] % 10 == 0:
            print(f"    calibration eval {eval_count[0]:3d}  loss={loss:.4f}  best={best[0]:4f}")
        return loss

    result = minimize(
        objective,
        x0,
        method=method,
        bounds=PARAM_BOUNDS,
        options={"maxiter": maxiter, "ftol": 1e-4},
    )
    return np.asarray(result.x, dtype=float), result


def save_calibrated_params(params: np.ndarray, path: Path | None = None) -> Path:
    """Persist optimal hyperparameters for production simulator."""
    path = path or CALIBRATED_PARAMS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time_decay_factor": float(params[0]),
        "home_advantage_baseline": float(params[1]),
        "chemistry_weight": float(params[2]),
        "h2h_weight": float(params[3]),
        "params": [float(x) for x in params],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_calibrated_params(path: Path | None = None) -> np.ndarray | None:
    path = path or CALIBRATED_PARAMS_PATH
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return np.asarray(data.get("params", []), dtype=float)


def apply_calibrated_params(engine: AdvancedFootballSimulator) -> AdvancedFootballSimulator:
    """Apply saved calibration to a simulator instance if available."""
    params = load_calibrated_params()
    if params is not None and len(params) == 4:
        engine.apply_params(params)
    return engine


# ---------------------------------------------------------------------------
# Synthetic 10-year dataset (6-team league, 2016–2025)
# ---------------------------------------------------------------------------

def generate_synthetic_historical_data(
    *,
    seed: int = 42,
    truth_params: np.ndarray | None = None,
) -> HistoricalSeasonData:
    """
    Build realistic synthetic 2016–2025 data for a 6-team league.

    Ground-truth match results are generated with hidden `truth_params`
    so calibration has a meaningful target to recover.
    """
    rng = np.random.default_rng(seed)
    teams = [
        "Crimson FC",
        "Azure United",
        "Verdant City",
        "Amber Town",
        "Violet Athletic",
        "Copper Rovers",
    ]
    base_strength = {
        "Crimson FC": 0.88,
        "Azure United": 0.78,
        "Verdant City": 0.72,
        "Amber Town": 0.62,
        "Violet Athletic": 0.52,
        "Copper Rovers": 0.42,
    }
    drift = {t: rng.uniform(-0.008, 0.012) for t in teams}
    truth = np.asarray(
        truth_params if truth_params is not None else [0.42, 0.28, 0.38, 0.18],
        dtype=float,
    )

    archive = HistoricalSeasonData()
    prior: list[SeasonRecord] = []

    for year in range(2016, 2026):
        team_parameters: dict[str, TeamSeasonParameters] = {}
        for t in teams:
            cap = float(np.clip(
                base_strength[t] + drift[t] * (year - 2016) + rng.normal(0, 0.03),
                0.25, 0.97,
            ))
            mgr = float(np.clip(0.50 + (cap - 0.5) * 0.6 + rng.normal(0, 0.04), 0.35, 0.95))
            players: dict[str, float] = {}
            health: dict[str, float] = {}
            starter_ids: list[str] = []
            for i in range(5):
                pid = f"{t}|p{i}"
                players[pid] = float(np.clip(cap + rng.normal(0, 0.06), 0.2, 0.98))
                h = 1.0 if rng.random() > 0.12 else rng.uniform(0.55, 0.78)
                health[pid] = h
                starter_ids.append(pid)
            team_parameters[t] = TeamSeasonParameters(
                team_id=t,
                squad_capability=cap,
                manager_skill=mgr,
                player_capabilities=players,
                player_health=health,
                starters=starter_ids,
            )

        fixtures = _double_round_robin(teams)
        season_stub = SeasonRecord(
            year=year,
            team_parameters=team_parameters,
            fixtures=fixtures,
            match_results=[],
            actual_table=pd.DataFrame(),
        )
        eng = seed_simulator_from_season(season_stub, prior, params=truth)
        gen = np.random.default_rng(seed + year)
        results: list[tuple[str, str, int, int]] = []
        for home, away in fixtures:
            res = eng.simulate_match(home, away, gen)
            results.append((home, away, res.home_goals, res.away_goals))

        actual_table = _table_from_results(teams, results)
        record = SeasonRecord(
            year=year,
            team_parameters=team_parameters,
            fixtures=fixtures,
            match_results=results,
            actual_table=actual_table,
        )
        archive.seasons.append(record)
        prior.append(record)

    return archive


def season_prediction_table(metrics: dict[str, Any]) -> pd.DataFrame:
    """Extract team / expected_points from a single-season backtest result."""
    pred = metrics["predicted"]
    return pred[["team", "expected_points", "position"]].copy()


# ---------------------------------------------------------------------------
# Execution pipeline
# ---------------------------------------------------------------------------

def _comparison_table_2025(
    historical_data: HistoricalSeasonData,
    default_metrics: list[dict[str, Any]],
    calibrated_metrics: list[dict[str, Any]],
) -> pd.DataFrame:
    season = historical_data.get(2025)
    if season is None:
        season = historical_data.seasons[-1]

    actual = season.actual_table.set_index("team")["points"]
    old_pred = default_metrics[-1]["predicted"].set_index("team")["expected_points"]
    new_pred = calibrated_metrics[-1]["predicted"].set_index("team")["expected_points"]

    rows = []
    for team in sorted(actual.index):
        rows.append({
            "Team": team,
            "Actual Points": int(actual[team]),
            "Old Model Prediction": round(float(old_pred[team]), 1),
            "Calibrated Model Prediction": round(float(new_pred[team]), 1),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="10-year backtest & self-calibration")
    parser.add_argument("--pl", action="store_true", help="Use real PL CSV history instead of synthetic")
    parser.add_argument("--calibrate-only", action="store_true", help="Run calibration and save params only")
    parser.add_argument("--simulations", type=int, default=500, help="MC iterations for MC backtest steps")
    parser.add_argument("--max-seasons", type=int, default=None, help="Limit PL seasons (most recent N)")
    args = parser.parse_args()

    print("=" * 72)
    print("  Advanced Football Simulator — 10-Year Backtest & Self-Calibration")
    print("=" * 72)

    if args.pl:
        from src.predict.pl_historical_loader import build_premier_league_historical_data
        print("\nLoading Premier League historical data from CSVs...")
        historical = build_premier_league_historical_data(max_seasons=args.max_seasons)
    else:
        print("\nGenerating synthetic 6-team league data (2016–2025)...")
        historical = generate_synthetic_historical_data(seed=42)

    print(f"  Seasons: {historical.years()[0]}–{historical.years()[-1]}  "
          f"| Teams/season: ~{len(historical.seasons[0].team_parameters)}  "
          f"| Fixtures/season: {len(historical.seasons[0].fixtures)}")

    default_params = INITIAL_PARAMS.copy()

    if not args.calibrate_only:
        print("\n--- Step 1: Running Baseline 10-Year Backtest with Default Parameters ---")
        baseline_loss, baseline_metrics = run_10_year_backtest(
            default_params, historical, simulations=args.simulations, verbose=True,
        )
        baseline_rmse = float(np.mean([m["rmse"] for m in baseline_metrics]))
        print(f"\n  Total Average Combined Loss: {baseline_loss:.3f}")
        print(f"  Total Average RMSE (points):  {baseline_rmse:.3f}")
    else:
        baseline_loss, baseline_metrics = run_10_year_backtest(
            default_params, historical, simulations=0, analytical=True,
        )
        baseline_rmse = float(np.mean([m["rmse"] for m in baseline_metrics]))

    print("\n--- Step 2: Executing Automated Parameter Calibration (Self-Modification Loop) ---")
    print("  Optimizer: L-BFGS-B  |  Analytical expected points  |  maxiter: 25")
    optimal_params, opt_result = calibrate_model(
        historical,
        initial_params=default_params,
        simulations=0,
        maxiter=25,
    )
    print(f"\n  Optimization success: {opt_result.success}  |  Iterations: {opt_result.nit}")
    saved = save_calibrated_params(optimal_params)
    print(f"  Saved calibrated params → {saved}")
    print("\n  Newly Discovered Optimal Hyperparameter Weights:")
    labels = ["time_decay_factor", "home_advantage_baseline", "chemistry_weight", "h2h_weight"]
    for label, old, new in zip(labels, default_params, optimal_params):
        print(f"    {label:28s}  {old:.4f}  →  {new:.4f}")

    if args.calibrate_only:
        print("\n" + "=" * 72)
        raise SystemExit(0)

    print("\n--- Step 3: Verifying Calibrated Algorithm on Historical Dataset ---")
    calibrated_loss, calibrated_metrics = run_10_year_backtest(
        optimal_params, historical, simulations=args.simulations, verbose=True,
    )
    calibrated_rmse = float(np.mean([m["rmse"] for m in calibrated_metrics]))
    improvement = (1.0 - calibrated_loss / baseline_loss) * 100.0 if baseline_loss > 0 else 0.0
    rmse_improvement = (1.0 - calibrated_rmse / baseline_rmse) * 100.0 if baseline_rmse > 0 else 0.0

    print(f"\n  Baseline combined loss:   {baseline_loss:.3f}")
    print(f"  Calibrated combined loss: {calibrated_loss:.3f}")
    print(f"  Combined-loss improvement: {improvement:+.1f}%")
    print(f"  RMSE improvement:          {rmse_improvement:+.1f}%")

    target_year = historical.years()[-1]
    print(f"\n  {target_year} Season — Side-by-Side Comparison:")
    cmp = _comparison_table_2025(historical, baseline_metrics, calibrated_metrics)
    print(cmp.to_string(index=False))
    print("\n" + "=" * 72)
