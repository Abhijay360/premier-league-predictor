"""Per-fixture insights for the match detail page.

Keeps the heavy UI on the client, but provides all computed numbers:
- xG (λ/μ)
- outcome probabilities
- scoreline heatmap probabilities
- recent form metrics (win rate, goals, clean sheets)
- explanation strings and a confidence indicator
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson

from src.config import PREDICT_SEASON, TRAIN_SEASONS, get_paths
from src.dataio import load_raw_seasons


@dataclass(frozen=True)
class TeamRecentForm:
    games: int
    wins: int
    draws: int
    losses: int
    gf: int
    ga: int
    clean_sheets: int

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def gf_per_game(self) -> float:
        return self.gf / self.games if self.games else 0.0

    @property
    def ga_per_game(self) -> float:
        return self.ga / self.games if self.games else 0.0

    @property
    def gd_per_game(self) -> float:
        return (self.gf - self.ga) / self.games if self.games else 0.0

    @property
    def clean_sheet_rate(self) -> float:
        return self.clean_sheets / self.games if self.games else 0.0


def _recent_form(df: pd.DataFrame, team: str, n: int = 5) -> TeamRecentForm:
    # Uses the most recent played matches across TRAIN_SEASONS.
    played = df.dropna(subset=["FTHG", "FTAG", "FTR"]).copy()
    home = played[played["HomeTeam"] == team].copy()
    away = played[played["AwayTeam"] == team].copy()

    home["gf"] = home["FTHG"].astype(int)
    home["ga"] = home["FTAG"].astype(int)
    home["res"] = home["FTR"].astype(str)

    away["gf"] = away["FTAG"].astype(int)
    away["ga"] = away["FTHG"].astype(int)
    away["res"] = away["FTR"].astype(str).map({"H": "A", "A": "H", "D": "D"})

    both = pd.concat([home[["Date", "gf", "ga", "res"]], away[["Date", "gf", "ga", "res"]]], ignore_index=True)
    both = both.sort_values("Date").tail(n)
    if len(both) == 0:
        return TeamRecentForm(games=0, wins=0, draws=0, losses=0, gf=0, ga=0, clean_sheets=0)

    wins = int((both["res"] == "H").sum())
    draws = int((both["res"] == "D").sum())
    losses = int((both["res"] == "A").sum())
    gf = int(both["gf"].sum())
    ga = int(both["ga"].sum())
    cs = int((both["ga"] == 0).sum())
    return TeamRecentForm(games=int(len(both)), wins=wins, draws=draws, losses=losses, gf=gf, ga=ga, clean_sheets=cs)


def score_heatmap(lam_home: float, lam_away: float, max_goals: int = 5) -> dict:
    """Return scoreline probability grid for 0..max_goals goals each."""
    h = np.arange(max_goals + 1)
    ph = poisson.pmf(h, lam_home)
    pa = poisson.pmf(h, lam_away)
    grid = np.outer(ph, pa)
    grid = grid / grid.sum() if grid.sum() > 0 else grid
    return {
        "max_goals": int(max_goals),
        "home_goals": [int(x) for x in h.tolist()],
        "away_goals": [int(x) for x in h.tolist()],
        "p": [[float(grid[i, j]) for j in range(max_goals + 1)] for i in range(max_goals + 1)],
    }


def confidence_from_probs(p_home: float, p_draw: float, p_away: float) -> dict:
    top = float(max(p_home, p_draw, p_away))
    second = float(sorted([p_home, p_draw, p_away], reverse=True)[1])
    gap = top - second
    if gap >= 0.18:
        label = "High confidence"
    elif gap >= 0.10:
        label = "Medium confidence"
    else:
        label = "Low confidence"
    return {"label": label, "gap": float(gap), "top_prob": float(top)}


def explain_match(home: str, away: str, home_form: TeamRecentForm, away_form: TeamRecentForm, lam: float, mu: float) -> list[dict]:
    """Simple explanation blocks for the UI."""
    out: list[dict] = []
    if home_form.clean_sheet_rate > away_form.clean_sheet_rate + 0.2:
        out.append({
            "title": "Defensive strength",
            "badge": f"{home} tighter defence",
            "detail": f"{home} kept clean sheets in {int(round(home_form.clean_sheet_rate*100))}% of recent games, suppressing opponent xG.",
        })
    if home_form.gd_per_game > away_form.gd_per_game + 0.6:
        out.append({
            "title": "Goal difference per game",
            "badge": f"{home} dominant",
            "detail": f"{home} carried +{home_form.gd_per_game:.2f} GD/game recently vs {away_form.gd_per_game:+.2f} for {away}.",
        })
    # xG note
    out.append({
        "title": "Expected goals (xG)",
        "badge": "Dixon–Coles rates",
        "detail": f"Model rates: {home} {lam:.2f} xG, {away} {mu:.2f} xG.",
    })
    return out[:3]


def fixture_insights(
    fixture_row: dict,
    *,
    season: str = PREDICT_SEASON,
    recent_n: int = 5,
) -> dict:
    """Compute all match insights from a fixture record + historical results."""
    home = str(fixture_row["HomeTeam"])
    away = str(fixture_row["AwayTeam"])
    lam = float(fixture_row.get("dc_lambda") or fixture_row.get("pred_home_xg") or 1.4)
    mu = float(fixture_row.get("dc_mu") or fixture_row.get("pred_away_xg") or 1.2)
    p_home = float(fixture_row.get("p_home") or 0.33)
    p_draw = float(fixture_row.get("p_draw") or 0.23)
    p_away = float(fixture_row.get("p_away") or 0.33)

    # History for recent form uses training seasons only (no look-ahead into predicted season).
    hist = load_raw_seasons(TRAIN_SEASONS)
    home_form = _recent_form(hist, home, n=recent_n)
    away_form = _recent_form(hist, away, n=recent_n)

    return {
        "home": home,
        "away": away,
        "xg": {"home": lam, "away": mu},
        "probs": {"home": p_home, "draw": p_draw, "away": p_away},
        "confidence": confidence_from_probs(p_home, p_draw, p_away),
        "form": {
            "recent_n": int(recent_n),
            "home": {
                "wins": home_form.wins,
                "draws": home_form.draws,
                "losses": home_form.losses,
                "gf_per_game": home_form.gf_per_game,
                "ga_per_game": home_form.ga_per_game,
                "clean_sheet_rate": home_form.clean_sheet_rate,
                "gd_per_game": home_form.gd_per_game,
            },
            "away": {
                "wins": away_form.wins,
                "draws": away_form.draws,
                "losses": away_form.losses,
                "gf_per_game": away_form.gf_per_game,
                "ga_per_game": away_form.ga_per_game,
                "clean_sheet_rate": away_form.clean_sheet_rate,
                "gd_per_game": away_form.gd_per_game,
            },
        },
        "score_heatmap": score_heatmap(lam, mu, max_goals=5),
        "explanations": explain_match(home, away, home_form, away_form, lam, mu),
    }

