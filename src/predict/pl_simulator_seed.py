"""Seed AdvancedFootballSimulator from Premier League squad and history data."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.config import PREDICT_SEASON, TRAIN_SEASONS
from src.dataio import load_raw_seasons
from src.ingest.fetch_squad_data import load_squad_data
from src.manager_adjustments import MANAGER_BOOST
from src.predict.advanced_simulator import AdvancedFootballSimulator
from src.predict.backtest_calibration import apply_calibrated_params

# Position weights for attack vs defence composites
_ATTACK_POS = {"FW", "AM", "LW", "RW", "CF", "SS"}
_DEFENCE_POS = {"GK", "CB", "LB", "RB", "WB", "DM"}


def _player_id(team: str, name: str) -> str:
    return f"{team}|{name}"


def _capability_from_value(value_m: float, league_max: float) -> float:
    if league_max <= 0:
        return 0.5
    raw = value_m / league_max
    return float(np.clip(0.25 + raw * 0.70, 0.20, 0.98))


def _manager_skill(team: str) -> float:
    boost = MANAGER_BOOST.get(team, 0.0)
    return float(np.clip(0.55 + boost * 1.8, 0.40, 0.96))


def _position_weights(position: str) -> tuple[float, float]:
    pos = (position or "").upper()
    if any(p in pos for p in _ATTACK_POS):
        return 1.15, 0.82
    if any(p in pos for p in _DEFENCE_POS):
        return 0.82, 1.18
    return 1.0, 1.0


class PremierLeagueSimulatorSeed:
    """Build a seeded AdvancedFootballSimulator for the predict season."""

    def __init__(self, season: str = PREDICT_SEASON, train_seasons: list[str] | None = None):
        self.season = season
        self.train_seasons = train_seasons or TRAIN_SEASONS

    def build(self) -> AdvancedFootballSimulator:
        squad = load_squad_data(self.season)
        if not squad:
            raise FileNotFoundError(
                f"Squad data missing for {self.season}. Run fetch_squad_data first."
            )

        eng = AdvancedFootballSimulator()
        apply_calibrated_params(eng)
        player_max_mv = max(
            (
                float(p.get("market_value_m", 0))
                for t in squad.values()
                for p in t.get("players", [])
            ),
            default=1.0,
        )

        # Managers
        for team in squad:
            mgr_id = f"mgr|{team}"
            eng.register_manager(mgr_id, _manager_skill(team))

        # Players & rosters
        for team, data in squad.items():
            players = data.get("players", [])
            roster: list[str] = []
            starter_ids: list[str] = []
            top11 = sorted(players, key=lambda p: p.get("market_value_m", 0), reverse=True)[:11]

            for p in players:
                pid = _player_id(team, p["name"])
                cap = _capability_from_value(float(p.get("market_value_m", 0)), player_max_mv)
                eng.register_player(pid, cap)
                atk_w, def_w = _position_weights(p.get("position", ""))
                eng.player_attack_weight[pid] = atk_w
                eng.player_defence_weight[pid] = def_w
                roster.append(pid)

            for p in top11:
                starter_ids.append(_player_id(team, p["name"]))

            if not starter_ids and roster:
                starter_ids = roster[:11]

            eng.register_team(team, roster, f"mgr|{team}", starters=starter_ids)
            eng.team_squad_boost[team] = float(data.get("squad_boost", 0.5))

        self._seed_h2h(eng)
        return eng

    def _seed_h2h(self, eng: AdvancedFootballSimulator) -> None:
        try:
            history = load_raw_seasons(self.train_seasons)
        except FileNotFoundError:
            return

        history = history.dropna(subset=["FTHG", "FTAG"])
        ref = datetime(2000 + int(self.season[:2]), 7, 1)

        for _, r in history.iterrows():
            home = str(r["HomeTeam"])
            away = str(r["AwayTeam"])
            dt = pd.Timestamp(r["Date"]).to_pydatetime()
            age_years = max(0.0, (ref - dt).days / 365.25)
            eng.register_h2h_match(
                home, away,
                int(r["FTHG"]), int(r["FTAG"]),
                age_years=age_years,
            )
