"""Map current-squad data to team strength for prediction-time adjustments."""

from __future__ import annotations

import numpy as np

from src.ingest.fetch_squad_data import load_squad_data
from src.manager_adjustments import manager_boost

# How much current squad outweighs last season's results when predicting a new campaign
CURRENT_SQUAD_WEIGHT = 0.60


def transfer_momentum(net_spend_m: float, spend_in_m: float = 0.0) -> float:
    """
    Extra strength boost for clubs that heavily reinvested in the summer window.
    Spurs-style €150m+ net spend should materially lift projections.
    """
    if spend_in_m < 50 and net_spend_m < 30:
        return float(np.clip(net_spend_m / 250.0, -0.04, 0.04))
    momentum = 0.04 + net_spend_m / 100.0 * 0.07 + spend_in_m / 200.0 * 0.05
    return float(np.clip(momentum, -0.05, 0.20))


def effective_squad_boost(squad_boost: float, net_spend_m: float, spend_in_m: float = 0.0) -> float:
    return float(np.clip(squad_boost + transfer_momentum(net_spend_m, spend_in_m), 0.15, 0.98))


def squad_implied_ppg(squad_boost: float, manager_b: float = 0.0, net_spend_m: float = 0.0, spend_in_m: float = 0.0) -> float:
    """
    Convert squad boost (0–1) to expected points per game.
    Calibrated: elite squads ~2.0–2.2 ppg, mid-table ~1.3–1.5, relegation ~0.9–1.1.
    """
    eff = effective_squad_boost(squad_boost, net_spend_m, spend_in_m)
    base = 0.75 + (eff - 0.25) * 1.85
    return float(np.clip(base + manager_b * 0.45, 0.85, 2.35))


def squad_implied_elo(squad_boost: float, manager_b: float = 0.0, net_spend_m: float = 0.0, spend_in_m: float = 0.0) -> float:
    """Elo offset from squad quality relative to league average."""
    eff = effective_squad_boost(squad_boost, net_spend_m, spend_in_m)
    return 1500.0 + (eff - 0.5) * 280.0 + manager_b * 70.0


def get_team_squad_strength(team: str, squad_lookup: dict | None = None) -> dict[str, float]:
    from src.config import PREDICT_SEASON

    lookup = squad_lookup or load_squad_data(PREDICT_SEASON)
    s = lookup.get(team, {})
    boost = float(s.get("squad_boost", 0.5))
    mgr = manager_boost(team)
    net = float(s.get("net_spend_m", 0.0))
    spend_in = float(s.get("spend_in_m", 0.0))
    eff = effective_squad_boost(boost, net, spend_in)
    return {
        "squad_boost": boost,
        "effective_boost": eff,
        "transfer_momentum": transfer_momentum(net, spend_in),
        "implied_ppg": squad_implied_ppg(boost, mgr, net, spend_in),
        "implied_elo": squad_implied_elo(boost, mgr, net, spend_in),
        "net_spend_m": net,
        "spend_in_m": spend_in,
        "top11_value_m": float(s.get("top11_value_m", 0.0)),
    }


def blend_with_squad(
    historical_ppg: float,
    squad_boost: float,
    manager_b: float = 0.0,
    net_spend_m: float = 0.0,
    spend_in_m: float = 0.0,
) -> float:
    """Blend last-season form with current-squad implied strength."""
    implied = squad_implied_ppg(squad_boost, manager_b, net_spend_m, spend_in_m)
    w = CURRENT_SQUAD_WEIGHT
    return (1 - w) * historical_ppg + w * implied


def adjust_match_probabilities(
    p_home: float,
    p_draw: float,
    p_away: float,
    home_boost: float,
    away_boost: float,
) -> tuple[float, float, float]:
    """
    Post-model adjustment: shift win probability by squad-strength gap.
    Draw probability absorbs some of the shift (realistic — favorites win more, don't eliminate draws).
    """
    gap = home_boost - away_boost
    shift = float(np.clip(gap * 0.28, -0.22, 0.22))

    p = np.array([p_home, p_draw, p_away], dtype=float)
    p[0] += shift * 0.75
    p[2] -= shift * 0.75
    # Slightly reduce draw when there's a big squad mismatch
    if abs(gap) > 0.15:
        draw_take = abs(gap) * 0.04
        p[1] = max(0.12, p[1] - draw_take)
        if gap > 0:
            p[0] += draw_take * 0.6
            p[2] += draw_take * 0.4
        else:
            p[2] += draw_take * 0.6
            p[0] += draw_take * 0.4

    p = np.clip(p, 1e-6, 1.0)
    p /= p.sum()
    return float(p[0]), float(p[1]), float(p[2])
