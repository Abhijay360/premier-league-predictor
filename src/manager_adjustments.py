"""Manager-change strength adjustments for the predict season.

Applied at prediction time only (not in historical training).
Values are Elo-equivalent boosts on a 0–1 scale (0.10 ≈ +12 Elo).
"""

from __future__ import annotations

# 2026–27 appointments / high-impact manager changes
MANAGER_BOOST: dict[str, float] = {
    "Chelsea": 0.18,       # Xabi Alonso — elite tactical upgrade
    "Tottenham": 0.12,     # Major squad rebuild + €150m net spend
    "Man United": 0.05,    # Stabilised under new regime
    "West Ham": 0.04,      # Nuno Espírito Santo
    "Leeds": 0.06,         # Promotion + new manager energy
    "Sunderland": 0.05,    # Promotion momentum
}

MANAGER_NOTES: dict[str, str] = {
    "Chelsea": "Xabi Alonso appointment (+ squad spend)",
    "Tottenham": "Squad refresh + manager change",
    "Man United": "Continuity under current setup",
}


def manager_boost(team: str) -> float:
    return MANAGER_BOOST.get(team, 0.0)


def manager_note(team: str) -> str | None:
    return MANAGER_NOTES.get(team)
