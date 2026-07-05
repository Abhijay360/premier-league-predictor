"""
Advanced Football Season Simulation Engine.

Three-layer stack:
  1. Feature engineering & dynamic team-state vectors
  2. Modified Dixon-Coles / Poisson match engine
  3. Monte Carlo full-season simulation

Dependencies: numpy, pandas, scipy only (no sklearn/xgboost).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.stats import poisson


@dataclass
class MatchResult:
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int

    @property
    def outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "H"
        if self.home_goals < self.away_goals:
            return "A"
        return "D"


@dataclass
class AdvancedFootballSimulator:
    """
    Production-ready football season simulator with granular feature layers
    and Dixon-Coles Poisson match modelling.
    """

    # Dixon-Coles log-linear coefficients
    log_base_rate: float = np.log(1.35)
    attack_coef: float = 1.85
    defence_coef: float = 1.65
    home_advantage_baseline: float = 0.22
    h2h_coef: float = 0.12
    h2h_decay: float = 0.35
    chemistry_weight: float = 0.55
    max_goals: int = 10

    # Layer 1 state — static 10-year normalized ratings (0.0 → 1.0)
    player_capabilities: dict[str, float] = field(default_factory=dict)
    manager_skills: dict[str, float] = field(default_factory=dict)
    # h2h key: (home_id, away_id) -> list of (goal_diff_home_perspective, age_years)
    h2h_records: dict[tuple[str, str], list[tuple[float, float]]] = field(default_factory=dict)

    # Dynamic modifiers
    player_health: dict[str, float] = field(default_factory=dict)
    team_rosters: dict[str, list[str]] = field(default_factory=dict)
    team_managers: dict[str, str] = field(default_factory=dict)
    team_starters: dict[str, list[str]] = field(default_factory=dict)
    player_attack_weight: dict[str, float] = field(default_factory=dict)
    player_defence_weight: dict[str, float] = field(default_factory=dict)
    team_squad_boost: dict[str, float] = field(default_factory=dict)
    _composite_cache: dict[str, tuple[float, float]] = field(default_factory=dict, repr=False)

    def apply_params(self, params: np.ndarray | list[float]) -> None:
        """
        Inject tunable hyperparameters from the calibration engine.

        params[0] = time_decay_factor   → h2h_decay
        params[1] = home_advantage_baseline
        params[2] = chemistry_weight
        params[3] = h2h_weight          → h2h_coef
        """
        p = np.asarray(params, dtype=float).ravel()
        self.h2h_decay = float(p[0])
        self.home_advantage_baseline = float(p[1])
        self.chemistry_weight = float(p[2])
        self.h2h_coef = float(p[3])
        self._composite_cache.clear()

    @staticmethod
    def default_params() -> np.ndarray:
        return np.array([0.35, 0.22, 0.55, 0.12], dtype=float)

    def clone_empty(self) -> AdvancedFootballSimulator:
        """Fresh simulator shell preserving only coefficient settings."""
        return AdvancedFootballSimulator(
            log_base_rate=self.log_base_rate,
            attack_coef=self.attack_coef,
            defence_coef=self.defence_coef,
            home_advantage_baseline=self.home_advantage_baseline,
            h2h_coef=self.h2h_coef,
            h2h_decay=self.h2h_decay,
            chemistry_weight=self.chemistry_weight,
            max_goals=self.max_goals,
        )

    # ------------------------------------------------------------------
    # Layer 1 — registration & feature engineering
    # ------------------------------------------------------------------

    def register_player(self, player_id: str, capability: float) -> None:
        self.player_capabilities[player_id] = float(np.clip(capability, 0.0, 1.0))
        self.player_health.setdefault(player_id, 1.0)

    def register_manager(self, manager_id: str, skill: float) -> None:
        self.manager_skills[manager_id] = float(np.clip(skill, 0.0, 1.0))

    def register_team(
        self,
        team_id: str,
        roster: list[str],
        manager_id: str,
        starters: list[str] | None = None,
    ) -> None:
        self.team_rosters[team_id] = list(roster)
        self.team_managers[team_id] = manager_id
        self.team_starters[team_id] = list(starters or roster[:11])

    def set_player_health(self, player_id: str, health: float) -> None:
        self.player_health[player_id] = float(np.clip(health, 0.0, 1.0))

    def register_h2h_match(
        self,
        home_id: str,
        away_id: str,
        home_goals: int,
        away_goals: int,
        age_years: float = 0.0,
    ) -> None:
        key = (home_id, away_id)
        gd = float(home_goals - away_goals)
        self.h2h_records.setdefault(key, []).append((gd, age_years))

    @staticmethod
    def health_multiplier(health: float) -> float:
        """Non-linear penalty below 80% fitness (health^2)."""
        h = float(np.clip(health, 0.0, 1.0))
        if h < 0.8:
            return h * h
        return h

    def player_chemistry_multiplier(self, capabilities: np.ndarray) -> float:
        """
        Synergy from starting-XI capability variance.
        High std dev → lower chemistry.
        """
        if len(capabilities) == 0:
            return 0.85
        std = float(np.std(capabilities))
        # std≈0 → 1.0 synergy; chemistry_weight scales variance penalty
        synergy = 1.0 - std * self.chemistry_weight
        return float(np.clip(synergy, 0.70, 1.05))

    def manager_player_chemistry(self, manager_id: str, squad_mean: float) -> float:
        """Tactical multiplier from manager 10-year skill applied to squad baseline."""
        mgr = self.manager_skills.get(manager_id, 0.55)
        # Elite manager on strong squad gets larger uplift
        uplift = (mgr - 0.5) * 0.35 + (squad_mean - 0.5) * (mgr - 0.45) * 0.25
        return float(np.clip(1.0 + uplift, 0.82, 1.22))

    def _starting_xi_capabilities(self, team_id: str) -> np.ndarray:
        starters = self.team_starters.get(team_id, self.team_rosters.get(team_id, [])[:11])
        caps: list[float] = []
        for pid in starters:
            base = self.player_capabilities.get(pid, 0.5)
            health = self.player_health.get(pid, 1.0)
            caps.append(base * self.health_multiplier(health))
        if not caps:
            return np.array([0.5])
        return np.array(caps, dtype=float)

    def compute_composite_vectors(self, team_id: str) -> tuple[float, float]:
        """
        Aggregate squad strength, health, and chemistry into attack/defence floats.
        Returns (composite_attack, composite_defense) in [0, 1].
        """
        cached = self._composite_cache.get(team_id)
        if cached is not None:
            return cached

        starters = self.team_starters.get(team_id, self.team_rosters.get(team_id, [])[:11])
        atk_caps: list[float] = []
        def_caps: list[float] = []
        for pid in starters:
            base = self.player_capabilities.get(pid, 0.5)
            health = self.player_health.get(pid, 1.0)
            adj = base * self.health_multiplier(health)
            w_atk = self.player_attack_weight.get(pid, 1.0)
            w_def = self.player_defence_weight.get(pid, 1.0)
            atk_caps.append(adj * w_atk)
            def_caps.append(adj * w_def)

        if not atk_caps:
            boost = self.team_squad_boost.get(team_id, 0.5)
            return float(np.clip(boost, 0.15, 0.98)), float(np.clip(boost, 0.15, 0.98))

        atk_arr = np.array(atk_caps, dtype=float)
        def_arr = np.array(def_caps, dtype=float)
        squad_mean = float(np.mean(np.concatenate([atk_arr, def_arr])))
        chemistry = self.player_chemistry_multiplier(atk_arr)
        manager_id = self.team_managers.get(team_id, "")
        mgr_mult = self.manager_player_chemistry(manager_id, squad_mean)

        squad_boost = self.team_squad_boost.get(team_id, squad_mean)
        blend = 0.55 * squad_mean + 0.45 * squad_boost

        composite_attack = float(np.mean(atk_arr)) * chemistry * mgr_mult * (0.85 + 0.30 * blend)
        depth_bonus = 1.0 + max(0.0, 0.08 - float(np.std(def_arr)) * 0.2)
        composite_defense = float(np.mean(def_arr)) * chemistry * mgr_mult * depth_bonus * (0.85 + 0.30 * blend)

        result = (
            float(np.clip(composite_attack, 0.15, 0.98)),
            float(np.clip(composite_defense, 0.15, 0.98)),
        )
        self._composite_cache[team_id] = result
        return result

    def compute_h2h_modifier(self, home_team: str, away_team: str) -> float:
        """
        Time-decay weighted mean of historical H2H goal differences
        from the home team's perspective.
        """
        records = self.h2h_records.get((home_team, away_team), [])
        if not records:
            return 0.0
        weights = np.array([np.exp(-self.h2h_decay * age) for _, age in records], dtype=float)
        diffs = np.array([gd for gd, _ in records], dtype=float)
        if weights.sum() <= 0:
            return 0.0
        mean_gd = float(np.average(diffs, weights=weights))
        # Scale goal diff to log-rate modifier (typical range ±0.15)
        return float(np.clip(mean_gd * 0.04, -0.20, 0.20))

    # ------------------------------------------------------------------
    # Layer 2 — Dixon-Coles / Poisson match engine
    # ------------------------------------------------------------------

    def compute_dixon_coles_rates(self, home_team: str, away_team: str) -> tuple[float, float]:
        """
        Log-linear Poisson intensities:
          λ (home) = exp(base + attack_home - defence_away + home_adv + h2h)
          μ (away) = exp(base + attack_away - defence_home - h2h)
        """
        home_atk, home_def = self.compute_composite_vectors(home_team)
        away_atk, away_def = self.compute_composite_vectors(away_team)
        h2h = self.compute_h2h_modifier(home_team, away_team)

        log_lambda = (
            self.log_base_rate
            + self.attack_coef * (home_atk - 0.5)
            - self.defence_coef * (away_def - 0.5)
            + self.home_advantage_baseline
            + self.h2h_coef * h2h
        )
        log_mu = (
            self.log_base_rate
            + self.attack_coef * (away_atk - 0.5)
            - self.defence_coef * (home_def - 0.5)
            - self.h2h_coef * h2h
        )

        lam = float(np.exp(np.clip(log_lambda, -1.2, 1.8)))
        mu = float(np.exp(np.clip(log_mu, -1.2, 1.8)))
        return lam, mu

    def match_outcome_probabilities(
        self, home_team: str, away_team: str
    ) -> tuple[float, float, float]:
        """Analytical H/D/A probabilities from independent Poisson score grid."""
        lam, mu = self.compute_dixon_coles_rates(home_team, away_team)
        return self._outcome_probs_from_rates(lam, mu)

    @staticmethod
    def _outcome_probs_from_rates(lam: float, mu: float, max_g: int = 8) -> tuple[float, float, float]:
        """Vectorised Poisson score-grid outcome probabilities."""
        h = np.arange(max_g + 1)
        ph = poisson.pmf(h, lam)
        pa = poisson.pmf(h, mu)
        joint = np.outer(ph, pa)
        p_h = float(np.tril(joint, -1).sum())
        p_d = float(np.trace(joint))
        p_a = float(np.triu(joint, 1).sum())
        total = p_h + p_d + p_a
        if total <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return p_h / total, p_d / total, p_a / total

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        lam, mu = self.compute_dixon_coles_rates(home_team, away_team)
        return lam, mu

    def simulate_match(
        self,
        home_team: str,
        away_team: str,
        rng: np.random.Generator | None = None,
    ) -> MatchResult:
        """Draw discrete goals from Poisson(λ) and Poisson(μ)."""
        lam, mu = self.compute_dixon_coles_rates(home_team, away_team)
        gen = rng or np.random.default_rng()
        hg = int(poisson.rvs(lam, random_state=gen))
        ag = int(poisson.rvs(mu, random_state=gen))
        return MatchResult(home_team, away_team, hg, ag)

    # ------------------------------------------------------------------
    # Layer 3 — Monte Carlo season simulation
    # ------------------------------------------------------------------

    def run_monte_carlo_season(
        self,
        teams: Iterable[str],
        fixtures: list[tuple[str, str]],
        simulations: int = 10_000,
        seed: int | None = 42,
    ) -> pd.DataFrame:
        """
        Simulate the full fixture list N times.

        Returns DataFrame sorted by Expected Points with 95% confidence bounds,
        average goals scored and conceded.
        """
        return self._run_monte_carlo(
            list(teams),
            fixtures,
            simulations=simulations,
            seed=seed,
        )

    def _run_monte_carlo(
        self,
        team_list: list[str],
        fixtures: list[tuple[str, str]],
        simulations: int = 10_000,
        seed: int | None = 42,
    ) -> pd.DataFrame:
        n_sims = int(simulations)
        rng = np.random.default_rng(seed)

        # Precompute λ/μ once per fixture (composite state is static within a run)
        rates = [self.compute_dixon_coles_rates(h, a) for h, a in fixtures]

        points = {t: np.zeros(n_sims, dtype=float) for t in team_list}
        gf = {t: np.zeros(n_sims, dtype=float) for t in team_list}
        ga = {t: np.zeros(n_sims, dtype=float) for t in team_list}

        for sim_i in range(n_sims):
            sim_pts = {t: 0.0 for t in team_list}
            sim_gf = {t: 0.0 for t in team_list}
            sim_ga = {t: 0.0 for t in team_list}

            for (home, away), (lam, mu) in zip(fixtures, rates):
                hg = int(poisson.rvs(lam, random_state=rng))
                ag = int(poisson.rvs(mu, random_state=rng))
                sim_gf[home] += hg
                sim_ga[home] += ag
                sim_gf[away] += ag
                sim_ga[away] += hg

                if hg > ag:
                    sim_pts[home] += 3
                elif hg == ag:
                    sim_pts[home] += 1
                    sim_pts[away] += 1
                else:
                    sim_pts[away] += 3

            for t in team_list:
                points[t][sim_i] = sim_pts[t]
                gf[t][sim_i] = sim_gf[t]
                ga[t][sim_i] = sim_ga[t]

        rows = []
        for t in team_list:
            pts_arr = points[t]
            rows.append({
                "team": t,
                "expected_points": float(np.mean(pts_arr)),
                "points_p95_upper": float(np.percentile(pts_arr, 97.5)),
                "points_p95_lower": float(np.percentile(pts_arr, 2.5)),
                "avg_goals_scored": float(np.mean(gf[t])),
                "avg_goals_conceded": float(np.mean(ga[t])),
                "expected_gf": int(round(np.mean(gf[t]))),
                "expected_ga": int(round(np.mean(ga[t]))),
                "expected_gd": int(round(np.mean(gf[t]) - np.mean(ga[t]))),
            })

        df = pd.DataFrame(rows)
        df = df.sort_values(
            ["expected_points", "expected_gd", "avg_goals_scored"],
            ascending=False,
        ).reset_index(drop=True)
        df.insert(0, "position", np.arange(1, len(df) + 1))
        return df

    def predict_season_analytical(
        self,
        teams: Iterable[str],
        fixtures: list[tuple[str, str]],
    ) -> pd.DataFrame:
        """
        Deterministic season projection from Poisson outcome probabilities.
        Faster than Monte Carlo — used during parameter calibration.
        """
        team_list = list(teams)
        pts = {t: 0.0 for t in team_list}
        gf = {t: 0.0 for t in team_list}
        ga = {t: 0.0 for t in team_list}

        rates = [self.compute_dixon_coles_rates(h, a) for h, a in fixtures]
        for (home, away), (lam, mu) in zip(fixtures, rates):
            p_h, p_d, p_a = self._outcome_probs_from_rates(lam, mu, max_g=self.max_goals)
            pts[home] += 3.0 * p_h + p_d
            pts[away] += 3.0 * p_a + p_d
            gf[home] += lam
            ga[home] += mu
            gf[away] += mu
            ga[away] += lam

        rows = []
        for t in team_list:
            rows.append({
                "team": t,
                "expected_points": pts[t],
                "points_p95_upper": pts[t],
                "points_p95_lower": pts[t],
                "avg_goals_scored": gf[t],
                "avg_goals_conceded": ga[t],
                "expected_gf": int(round(gf[t])),
                "expected_ga": int(round(ga[t])),
                "expected_gd": int(round(gf[t] - ga[t])),
            })

        df = pd.DataFrame(rows)
        df = df.sort_values(
            ["expected_points", "expected_gd", "avg_goals_scored"],
            ascending=False,
        ).reset_index(drop=True)
        df.insert(0, "position", np.arange(1, len(df) + 1))
        return df


# ----------------------------------------------------------------------
# Demo / standalone execution
# ----------------------------------------------------------------------

def _build_demo_engine() -> AdvancedFootballSimulator:
    """Seed engine with realistic dummy data for Man City vs Arsenal demo."""
    eng = AdvancedFootballSimulator()

    # 3 top-tier managers
    eng.register_manager("mgr_guardiola", 0.94)
    eng.register_manager("mgr_arteta", 0.88)
    eng.register_manager("mgr_slot", 0.86)

    # 10 players with 10-year baseline capabilities
    players = {
        "p_haaland": 0.96,
        "p_debruyne": 0.91,
        "p_rodri": 0.93,
        "p_walker": 0.82,
        "p_dias": 0.90,
        "p_saka": 0.89,
        "p_odegaard": 0.88,
        "p_saliba": 0.87,
        "p_rice": 0.90,
        "p_jesus": 0.84,
    }
    for pid, cap in players.items():
        eng.register_player(pid, cap)

    # Man City XI
    city_roster = ["p_haaland", "p_debruyne", "p_rodri", "p_walker", "p_dias"]
    eng.register_team("Man City", city_roster, "mgr_guardiola", starters=city_roster)

    # Arsenal XI — Saka injured (health < 0.8 → health² penalty)
    arsenal_roster = ["p_saka", "p_odegaard", "p_saliba", "p_rice", "p_jesus"]
    eng.register_team("Arsenal", arsenal_roster, "mgr_arteta", starters=arsenal_roster)
    eng.set_player_health("p_saka", 0.65)  # key injury demo

    # Minimal H2H history (home-perspective goal diff, age in years)
    eng.register_h2h_match("Man City", "Arsenal", 3, 1, age_years=0.5)
    eng.register_h2h_match("Man City", "Arsenal", 2, 2, age_years=1.2)
    eng.register_h2h_match("Arsenal", "Man City", 1, 0, age_years=2.0)

    return eng


if __name__ == "__main__":
    engine = _build_demo_engine()

    teams = ["Man City", "Arsenal"]
    fixtures = [
        ("Man City", "Arsenal"),
        ("Arsenal", "Man City"),
    ]

    # Show live scenario diagnostics
    lam, mu = engine.compute_dixon_coles_rates("Man City", "Arsenal")
    city_atk, city_def = engine.compute_composite_vectors("Man City")
    ars_atk, ars_def = engine.compute_composite_vectors("Arsenal")
    p_h, p_d, p_a = engine.match_outcome_probabilities("Man City", "Arsenal")

    print("=== Live Scenario: Man City vs Arsenal ===")
    print(f"Man City composite: attack={city_atk:.3f}, defense={city_def:.3f}")
    print(f"Arsenal composite:  attack={ars_atk:.3f}, defense={ars_def:.3f}")
    print(f"  (Saka health=0.65 → non-linear penalty applied)")
    print(f"Dixon-Coles rates: λ={lam:.3f}, μ={mu:.3f}")
    print(f"Outcome probs: H={p_h:.1%} D={p_d:.1%} A={p_a:.1%}")
    print()

    print("=== Monte Carlo Season (10,000 iterations, double round-robin) ===")
    table = engine.run_monte_carlo_season(teams, fixtures, simulations=10_000, seed=42)
    print(table.to_string(index=False))
