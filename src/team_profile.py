"""Team profile: trophies, season history, and fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PREDICT_SEASON, TRAIN_SEASONS, get_paths
from src.dataio import load_parquet, load_raw_seasons
from src.manager_adjustments import MANAGER_BOOST, MANAGER_NOTES
from src.teams_meta import team_info


def _season_label(code: str) -> str:
    y1, y2 = int(code[:2]), int(code[2:])
    return f"20{y1}–{y2}"


def _load_trophies() -> dict[str, dict]:
    path = get_paths().data_dir / "club_trophies.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _team_season_history(team: str) -> list[dict[str, Any]]:
    hist = load_raw_seasons(TRAIN_SEASONS)
    rows: list[dict[str, Any]] = []
    for season in TRAIN_SEASONS:
        sdf = hist[hist["season"].astype(str) == season]
        if sdf.empty:
            continue
        home = sdf[sdf["HomeTeam"] == team]
        away = sdf[sdf["AwayTeam"] == team]
        if home.empty and away.empty:
            rows.append({
                "season": season,
                "label": _season_label(season),
                "played": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "gf": 0,
                "ga": 0,
                "gd": 0,
                "points": 0,
                "in_pl": False,
            })
            continue

        hw = int((home["FTR"] == "H").sum())
        aw = int((away["FTR"] == "A").sum())
        hd = int((home["FTR"] == "D").sum()) + int((away["FTR"] == "D").sum())
        hl = int((home["FTR"] == "A").sum()) + int((away["FTR"] == "A").sum())
        gf = int(home["FTHG"].sum()) + int(away["FTAG"].sum())
        ga = int(home["FTAG"].sum()) + int(away["FTHG"].sum())
        played = int(len(home) + len(away))
        pts = 3 * (hw + aw) + hd
        rows.append({
            "season": season,
            "label": _season_label(season),
            "played": played,
            "won": hw + aw,
            "drawn": hd,
            "lost": hl,
            "gf": gf,
            "ga": ga,
            "gd": gf - ga,
            "points": pts,
            "in_pl": True,
        })
    return rows


def _team_fixtures(team: str, season: str = PREDICT_SEASON) -> dict[str, list[dict]]:
    paths = get_paths()
    sim_path = paths.processed_dir / "season_simulation.parquet"
    if not sim_path.exists():
        return {"upcoming": [], "played": []}

    df = load_parquet(sim_path)
    mask = (df["HomeTeam"] == team) | (df["AwayTeam"] == team)
    df = df[mask].sort_values("Date")
    out = df.copy()
    for col in out.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        out[col] = out[col].dt.strftime("%Y-%m-%d")

    records = out.replace({pd.NA: None}).to_dict(orient="records")
    upcoming = [r for r in records if not r.get("played")]
    played = [r for r in records if r.get("played")]
    return {"upcoming": upcoming, "played": played}


def team_profile(team: str, *, season: str = PREDICT_SEASON) -> dict[str, Any]:
    info = team_info(team)
    trophies = _load_trophies().get(team, {})
    history = _team_season_history(team)
    fixtures = _team_fixtures(team, season=season)

    pl_seasons = [h for h in history if h["in_pl"]]
    best = max(pl_seasons, key=lambda h: h["points"], default=None)

    return {
        "team": team,
        "info": info,
        "trophies": trophies.get("trophies", []),
        "most_recent_major": trophies.get("most_recent_major"),
        "founded": trophies.get("founded"),
        "nickname": trophies.get("nickname"),
        "manager_boost": MANAGER_BOOST.get(team),
        "manager_note": MANAGER_NOTES.get(team),
        "season_history": history,
        "best_pl_season": best,
        "fixtures": fixtures,
        "predict_season": season,
        "predict_season_label": _season_label(season),
    }
