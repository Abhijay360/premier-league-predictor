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
    sequence: tuple[str, ...] = ()

    @property
    def form_points(self) -> int:
        return 3 * self.wins + self.draws

    @property
    def attack_efficiency(self) -> float:
        return self.gf_per_game

    @property
    def defensive_solidity(self) -> float:
        # Higher = tougher defence (scale ~4–10 for PL rates)
        return float(np.clip(10.0 - self.ga_per_game * 2.2, 3.0, 10.0))

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
        return TeamRecentForm(games=0, wins=0, draws=0, losses=0, gf=0, ga=0, clean_sheets=0, sequence=())

    wins = int((both["res"] == "H").sum())
    draws = int((both["res"] == "D").sum())
    losses = int((both["res"] == "A").sum())
    gf = int(both["gf"].sum())
    ga = int(both["ga"].sum())
    cs = int((both["ga"] == 0).sum())
    seq = tuple({"H": "W", "D": "D", "A": "L"}.get(str(r), str(r)) for r in both["res"].tolist())
    return TeamRecentForm(
        games=int(len(both)), wins=wins, draws=draws, losses=losses,
        gf=gf, ga=ga, clean_sheets=cs, sequence=seq,
    )


def _form_momentum(sequence: tuple[str, ...]) -> tuple[float, str]:
    """Recency-weighted form score in [-1, 1] and a short label."""
    if not sequence:
        return 0.0, "No recent data"
    weights = np.array([1.0, 0.85, 0.7, 0.55, 0.4, 0.3][: len(sequence)], dtype=float)
    weights = weights / weights.sum()
    pts = {"W": 1.0, "D": 0.15, "L": -1.0}
    raw = sum(weights[i] * pts.get(sequence[i], 0.0) for i in range(len(sequence)))
    score = float(np.clip(raw, -1.0, 1.0))
    if score >= 0.35:
        label = "Strong recent run"
    elif score >= 0.1:
        label = "Positive momentum"
    elif score <= -0.35:
        label = "Poor recent run"
    elif score <= -0.1:
        label = "Negative momentum"
    else:
        label = "Mixed recent results"
    return score, label


def _form_to_dict(f: TeamRecentForm) -> dict:
    mom, mom_label = _form_momentum(f.sequence)
    return {
        "wins": f.wins,
        "draws": f.draws,
        "losses": f.losses,
        "sequence": list(f.sequence),
        "gf_per_game": f.gf_per_game,
        "ga_per_game": f.ga_per_game,
        "clean_sheet_rate": f.clean_sheet_rate,
        "gd_per_game": f.gd_per_game,
        "win_rate": f.win_rate,
        "form_points": f.form_points,
        "attack_efficiency": f.attack_efficiency,
        "defensive_solidity": f.defensive_solidity,
        "momentum": mom,
        "momentum_label": mom_label,
    }


def _comparison_charts(home: TeamRecentForm, away: TeamRecentForm) -> list[dict]:
    return [
        {"key": "win_rate", "label": "Win Rate %", "home": home.win_rate * 100, "away": away.win_rate * 100, "fmt": "pct"},
        {"key": "form_points", "label": "Form Points", "home": float(home.form_points), "away": float(away.form_points), "fmt": "num"},
        {"key": "attack", "label": "Attack Efficiency", "home": home.attack_efficiency, "away": away.attack_efficiency, "fmt": "dec"},
        {"key": "defence", "label": "Def. Solidity", "home": home.defensive_solidity, "away": away.defensive_solidity, "fmt": "dec"},
    ]


def _win_probability_block(home: str, away: str, p_home: float, p_draw: float, p_away: float) -> dict:
    probs = {"home": p_home, "draw": p_draw, "away": p_away}
    favorite = max(probs, key=probs.get)
    fav_name = {"home": home, "draw": "Draw", "away": away}[favorite]
    return {
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "favorite": favorite,
        "favorite_name": fav_name,
        "favorite_prob": float(probs[favorite]),
    }


def _h2h(hist: pd.DataFrame, home: str, away: str, n: int = 5) -> dict:
    """Head-to-head from the perspective of `home` in this fixture."""
    played = hist.dropna(subset=["FTHG", "FTAG", "FTR"]).copy()
    mask = ((played["HomeTeam"] == home) & (played["AwayTeam"] == away)) | (
        (played["HomeTeam"] == away) & (played["AwayTeam"] == home)
    )
    df = played[mask].sort_values("Date").tail(n).reset_index(drop=True)
    if df.empty:
        return {
            "n": int(n),
            "matches": [],
            "summary": {
                "games": 0,
                "home_wins": 0,
                "draws": 0,
                "away_wins": 0,
                "gf_per_game": 0.0,
                "ga_per_game": 0.0,
                "btts_rate": 0.0,
                "clean_sheet_rate": 0.0,
            },
        }

    matches: list[dict] = []
    w = d = l = 0
    gf_total = ga_total = 0
    btts = cs = 0

    for _, r in df.iterrows():
        ht = str(r["HomeTeam"])
        at = str(r["AwayTeam"])
        fthg = int(r["FTHG"])
        ftag = int(r["FTAG"])
        date = r["Date"]
        date_str = pd.Timestamp(date).strftime("%Y-%m-%d") if pd.notna(date) else ""

        if ht == home:
            gf, ga = fthg, ftag
        else:
            gf, ga = ftag, fthg

        if gf > ga:
            res = "W"
            w += 1
        elif gf < ga:
            res = "L"
            l += 1
        else:
            res = "D"
            d += 1

        gf_total += gf
        ga_total += ga
        if fthg > 0 and ftag > 0:
            btts += 1
        if ga == 0:
            cs += 1

        matches.append(
            {
                "date": date_str,
                "season": str(r.get("season") or ""),
                "home_team": ht,
                "away_team": at,
                "score": f"{fthg}–{ftag}",
                "result_for_home": res,
                "gf_for_home": int(gf),
                "ga_for_home": int(ga),
            }
        )

    games = int(len(matches))
    return {
        "n": int(n),
        "matches": matches[::-1],  # newest first for the UI
        "summary": {
            "games": games,
            "home_wins": int(w),
            "draws": int(d),
            "away_wins": int(l),
            "gf_per_game": float(gf_total / games) if games else 0.0,
            "ga_per_game": float(ga_total / games) if games else 0.0,
            "btts_rate": float(btts / games) if games else 0.0,
            "clean_sheet_rate": float(cs / games) if games else 0.0,
        },
    }


def _norm_axis(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def _team_radar(home_form: TeamRecentForm, away_form: TeamRecentForm, lam: float, mu: float) -> dict:
    """Six-axis team comparison for the radar chart."""
    mom_h, _ = _form_momentum(home_form.sequence)
    mom_a, _ = _form_momentum(away_form.sequence)
    axis_defs = [
        ("raw_goals", "Raw Goals/Game", home_form.gf_per_game, away_form.gf_per_game, 0.0, 3.5),
        ("xg", "xG", lam, mu, 0.0, 3.2),
        ("momentum", "Form Momentum", (mom_h + 1.0) / 2.0, (mom_a + 1.0) / 2.0, 0.0, 1.0),
        ("gd", "Goal Diff/Game", home_form.gd_per_game, away_form.gd_per_game, -1.5, 2.5),
        ("cs", "Clean Sheet Rate", home_form.clean_sheet_rate, away_form.clean_sheet_rate, 0.0, 1.0),
        ("defence", "Defensive Solidity", home_form.defensive_solidity, away_form.defensive_solidity, 3.0, 10.0),
    ]
    axes = []
    for key, label, home_val, away_val, lo, hi in axis_defs:
        axes.append({
            "key": key,
            "label": label,
            "home": float(home_val),
            "away": float(away_val),
            "home_norm": _norm_axis(float(home_val), lo, hi),
            "away_norm": _norm_axis(float(away_val), lo, hi),
        })
    return {"axes": axes}


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
    h2h = _h2h(hist, home, away, n=8)

    conf = confidence_from_probs(p_home, p_draw, p_away)
    return {
        "home": home,
        "away": away,
        "xg": {"home": lam, "away": mu},
        "probs": {"home": p_home, "draw": p_draw, "away": p_away},
        "win_probability": _win_probability_block(home, away, p_home, p_draw, p_away),
        "confidence": conf,
        "form": {
            "recent_n": int(recent_n),
            "home": _form_to_dict(home_form),
            "away": _form_to_dict(away_form),
        },
        "h2h": h2h,
        "team_radar": _team_radar(home_form, away_form, lam, mu),
        "comparison_charts": _comparison_charts(home_form, away_form),
        "score_heatmap": score_heatmap(lam, mu, max_goals=5),
        "explanations": explain_match(home, away, home_form, away_form, lam, mu),
    }

