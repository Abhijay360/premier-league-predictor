"""Predict scoreline consistent with the predicted match outcome."""

from __future__ import annotations

import math


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _expected_lambdas(
    home_avg_gf: float,
    away_avg_gf: float,
    home_avg_ga: float,
    away_avg_ga: float,
) -> tuple[float, float]:
    lam_home = max(0.35, (home_avg_gf + away_avg_ga) / 2.0 * 0.95)
    lam_away = max(0.35, (away_avg_gf + home_avg_ga) / 2.0 * 0.85)
    return lam_home, lam_away


def match_expected_goals(
    home_avg_gf: float,
    away_avg_gf: float,
    home_avg_ga: float,
    away_avg_ga: float,
) -> tuple[float, float]:
    """Unconditional expected goals for table totals (sum across season)."""
    return _expected_lambdas(home_avg_gf, away_avg_gf, home_avg_ga, away_avg_ga)


def _conditional_expectation(
    lam_home: float,
    lam_away: float,
    outcome: str,
    max_g: int = 8,
) -> tuple[float, float]:
    """Expected goals given the predicted outcome H/D/A."""
    total_p = 0.0
    sum_h = 0.0
    sum_a = 0.0
    for h in range(max_g):
        for a in range(max_g):
            if outcome == "H" and h <= a:
                continue
            if outcome == "A" and a <= h:
                continue
            if outcome == "D" and h != a:
                continue
            p = _poisson_pmf(h, lam_home) * _poisson_pmf(a, lam_away)
            total_p += p
            sum_h += h * p
            sum_a += a * p
    if total_p < 1e-12:
        return lam_home, lam_away
    return sum_h / total_p, sum_a / total_p


def expected_scoreline_conditional(
    lam_home: float,
    lam_away: float,
    outcome: str,
    max_g: int = 8,
) -> tuple[int, int]:
    """
    Integer scoreline from conditional expected goals given H/D/A.

    The Poisson *mode* almost never exceeds 2 goals per team even when xG is
    high (3-0 is less likely than 2-0). Rounding E[goals | outcome] fixes that.
    """
    eh, ea = _conditional_expectation(lam_home, lam_away, outcome, max_g)
    h = int(round(eh))
    a = int(round(ea))
    # Rare 4-goal displays for very dominant matchups (xG gap >= ~1.8)
    if outcome == "H" and lam_home >= 2.85 and (lam_home - lam_away) >= 1.75 and eh >= 3.15:
        h = max(h, 4)
    elif outcome == "A" and lam_away >= 2.85 and (lam_away - lam_home) >= 1.75 and ea >= 3.15:
        a = max(a, 4)
    return _enforce_outcome(h, a, outcome)


def modal_scoreline_conditional(
    lam_home: float,
    lam_away: float,
    outcome: str,
    max_g: int = 8,
) -> tuple[int, int]:
    """
    Most likely integer scoreline given H/D/A outcome.
    Allows clean sheets (e.g. 2-0, 1-0) when Poisson mass supports them.
    """
    best_h, best_a, best_p = 0, 0, -1.0
    for h in range(max_g + 1):
        for a in range(max_g + 1):
            if outcome == "H" and h <= a:
                continue
            if outcome == "A" and a <= h:
                continue
            if outcome == "D" and h != a:
                continue
            p = _poisson_pmf(h, lam_home) * _poisson_pmf(a, lam_away)
            if p > best_p:
                best_p = p
                best_h, best_a = h, a
    if best_p < 0:
        h = max(0, int(round(lam_home)))
        a = max(0, int(round(lam_away)))
        return _enforce_outcome(h, a, outcome)
    return _enforce_outcome(best_h, best_a, outcome)


def _enforce_outcome(h: int, a: int, outcome: str) -> tuple[int, int]:
    if outcome == "H":
        if h <= a:
            a = max(0, h - 1) if h > 0 else 0
            h = max(h, a + 1)
            if h == 0:
                h = 1
    elif outcome == "A":
        if a <= h:
            h = max(0, a - 1) if a > 0 else 0
            a = max(a, h + 1)
            if a == 0:
                a = 1
    else:
        if h != a:
            m = max(0, round((h + a) / 2))
            h = a = m
            if h == 0 and a == 0:
                h = a = 1
    return h, a


def predict_scoreline(
    p_home: float,
    p_draw: float,
    p_away: float,
    home_avg_gf: float = 1.45,
    away_avg_gf: float = 1.45,
    home_avg_ga: float = 1.45,
    away_avg_ga: float = 1.45,
    outcome: str | None = None,
) -> tuple[int, int]:
    """
    Return a realistic integer scoreline matching the predicted outcome.
    Uses conditional expected goals (not the Poisson mode) so top teams
    still show occasional concessions instead of endless 2-0s.
    """
    from src.predict.outcomes import most_likely_outcome

    lam_home, lam_away = _expected_lambdas(home_avg_gf, away_avg_gf, home_avg_ga, away_avg_ga)
    pred = outcome or most_likely_outcome(p_home, p_draw, p_away)
    return expected_scoreline_conditional(lam_home, lam_away, pred)
