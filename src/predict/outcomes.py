"""Calibrate and sample match outcomes from model probabilities."""

from __future__ import annotations

import numpy as np

# Historical PL draw rate (~23%)
TARGET_DRAW_RATE = 0.23


def calibrate_probabilities(p_home: float, p_draw: float, p_away: float) -> tuple[float, float, float]:
    """
    Slightly boost draw probability so projected tables match historical W/D/L splits.
    Model often under-assigns draws when using argmax even when p_draw is reasonable.
    """
    p = np.array([p_home, p_draw, p_away], dtype=float)
    p = np.clip(p, 1e-6, 1.0)
    p /= p.sum()

    # Nudge draw toward historical average while preserving home/away ratio
    if p[1] < TARGET_DRAW_RATE:
        boost = TARGET_DRAW_RATE - p[1]
        take = boost * 0.5
        p[1] += boost
        p[0] = max(1e-6, p[0] - take * (p[0] / (p[0] + p[2] + 1e-9)))
        p[2] = max(1e-6, p[2] - take * (p[2] / (p[0] + p[2] + 1e-9)))
    p /= p.sum()
    return float(p[0]), float(p[1]), float(p[2])


def most_likely_outcome(p_home: float, p_draw: float, p_away: float) -> str:
    """Pick H/D/A from calibrated probabilities."""
    p_h, p_d, p_a = calibrate_probabilities(p_home, p_draw, p_away)
    idx = int(np.argmax([p_h, p_d, p_a]))
    return {0: "H", 1: "D", 2: "A"}[idx]


def sample_outcome(
    p_home: float,
    p_draw: float,
    p_away: float,
    rng: np.random.Generator,
) -> str:
    p_h, p_d, p_a = calibrate_probabilities(p_home, p_draw, p_away)
    idx = rng.choice(3, p=[p_h, p_d, p_a])
    return {0: "H", 1: "D", 2: "A"}[idx]


def integerize_wdl(w_float: float, d_float: float, l_float: float, total: int = 38) -> tuple[int, int, int]:
    """Convert fractional W/D/L to integers summing to total (Hamilton/largest remainder)."""
    fracs = [w_float, d_float, l_float]
    floors = [int(x) for x in fracs]
    remainder = total - sum(floors)
    order = sorted(range(3), key=lambda i: fracs[i] - floors[i], reverse=True)
    for i in range(remainder):
        floors[order[i]] += 1
    return floors[0], floors[1], floors[2]
