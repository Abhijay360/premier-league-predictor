"""Build projected league table from simulated season results."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.predict.outcomes import calibrate_probabilities, integerize_wdl


def build_standings_from_simulation(sim: pd.DataFrame) -> pd.DataFrame:
    """
    Build a realistic projected table using fractional W/D/L from calibrated
    match probabilities, then integerize per team. Points = 3W + D (integer).
    """
    stats: dict[str, dict] = {}

    def ensure(team: str) -> None:
        if team not in stats:
            stats[team] = {
                "p": 0, "w_f": 0.0, "d_f": 0.0, "l_f": 0.0,
                "gf_f": 0.0, "ga_f": 0.0, "pts_f": 0.0,
            }

    for _, r in sim.iterrows():
        home, away = str(r["HomeTeam"]), str(r["AwayTeam"])
        ensure(home)
        ensure(away)

        if r["played"]:
            hg, ag = int(r["FTHG"]), int(r["FTAG"])
            ftr = str(r["FTR"])
            p_h = 1.0 if ftr == "H" else 0.0
            p_d = 1.0 if ftr == "D" else 0.0
            p_a = 1.0 if ftr == "A" else 0.0
        else:
            p_h, p_d, p_a = calibrate_probabilities(
                float(r["p_home"]), float(r["p_draw"]), float(r["p_away"])
            )
            # Use expected goals for table totals — modal scorelines under-count concessions
            if pd.notna(r.get("pred_home_xg")) and pd.notna(r.get("pred_away_xg")):
                hg = float(r["pred_home_xg"])
                ag = float(r["pred_away_xg"])
            else:
                hg = float(r.get("pred_home_goals") or 0)
                ag = float(r.get("pred_away_goals") or 0)

        stats[home]["p"] += 1
        stats[home]["w_f"] += p_h
        stats[home]["d_f"] += p_d
        stats[home]["l_f"] += p_a
        stats[home]["gf_f"] += hg
        stats[home]["ga_f"] += ag
        stats[home]["pts_f"] += 3 * p_h + p_d

        stats[away]["p"] += 1
        stats[away]["w_f"] += p_a
        stats[away]["d_f"] += p_d
        stats[away]["l_f"] += p_h
        stats[away]["gf_f"] += ag
        stats[away]["ga_f"] += hg
        stats[away]["pts_f"] += 3 * p_a + p_d

    rows = []
    for team, s in stats.items():
        played = int(s["p"])
        w, d, l = integerize_wdl(s["w_f"], s["d_f"], s["l_f"], total=played)
        pts = 3 * w + d
        gf = int(round(s["gf_f"]))
        ga = int(round(s["ga_f"]))
        rows.append({
            "team": team,
            "played": played,
            "won": w,
            "drawn": d,
            "lost": l,
            "gf": gf,
            "ga": ga,
            "gd": gf - ga,
            "points": pts,
        })

    table = pd.DataFrame(rows).sort_values(["points", "gd", "gf"], ascending=False).reset_index(drop=True)
    table["position"] = np.arange(1, len(table) + 1)
    return table[["position", "team", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points"]]
