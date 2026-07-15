from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import PREDICT_SEASON, TRAIN_SEASONS, get_paths
from src.dataio import load_parquet
from src.ingest.fetch_squad_data import load_squad_data
from src.manager_adjustments import MANAGER_BOOST, MANAGER_NOTES
from src.standings import build_standings_from_simulation
from src.teams_meta import team_info, team_stadium, team_stadium_image
from src.train.train_model import FEATURE_COLS

paths = get_paths()
WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="Premier League Predictor", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df.copy()
    for col in out.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        out[col] = out[col].dt.strftime("%Y-%m-%d")
    return out.replace({np.nan: None}).to_dict(orient="records")


def _load_all_fixtures() -> pd.DataFrame:
    """Full season fixture list (played + upcoming)."""
    sim_path = paths.processed_dir / "season_simulation.parquet"
    if sim_path.exists():
        return load_parquet(sim_path).sort_values("Date").reset_index(drop=True)
    up_path = paths.processed_dir / "predictions_upcoming.parquet"
    if up_path.exists():
        return load_parquet(up_path).sort_values("Date").reset_index(drop=True)
    return pd.DataFrame()


def _find_fixture(home: str, away: str, date: str = "") -> pd.Series | None:
    df = _load_all_fixtures()
    if df.empty:
        return None
    mask = (df["HomeTeam"] == home) & (df["AwayTeam"] == away)
    if date:
        mask &= df["Date"].astype(str).str.startswith(date)
    rows = df[mask]
    if rows.empty:
        return None
    return rows.iloc[0]


def _search_fixtures(df: pd.DataFrame, q: str, limit: int = 25) -> pd.DataFrame:
    q = q.strip().lower()
    if not q:
        return df.head(limit)

    for sep in (" vs ", " v ", " - ", " @ "):
        if sep in q:
            left, right = (p.strip() for p in q.split(sep, 1))
            if left and right:
                home_hit = df["HomeTeam"].str.lower().str.contains(left, regex=False, na=False)
                away_hit = df["AwayTeam"].str.lower().str.contains(right, regex=False, na=False)
                fwd = home_hit & away_hit
                rev = (
                    df["HomeTeam"].str.lower().str.contains(right, regex=False, na=False)
                    & df["AwayTeam"].str.lower().str.contains(left, regex=False, na=False)
                )
                hits = df[fwd | rev]
                if len(hits):
                    return hits.head(limit)

    tokens = [t for t in q.replace("/", " ").split() if t]
    if len(tokens) >= 2:
        t1, t2 = tokens[0], " ".join(tokens[1:])
        fwd = (
            df["HomeTeam"].str.lower().str.contains(t1, regex=False, na=False)
            & df["AwayTeam"].str.lower().str.contains(t2, regex=False, na=False)
        )
        rev = (
            df["HomeTeam"].str.lower().str.contains(t2, regex=False, na=False)
            & df["AwayTeam"].str.lower().str.contains(t1, regex=False, na=False)
        )
        hits = df[fwd | rev]
        if len(hits):
            return hits.head(limit)

    mask = (
        df["HomeTeam"].str.lower().str.contains(q, regex=False, na=False)
        | df["AwayTeam"].str.lower().str.contains(q, regex=False, na=False)
    )
    if "stadium" in df.columns:
        mask |= df["stadium"].astype(str).str.lower().str.contains(q, regex=False, na=False)
    if "Round" in df.columns and q.isdigit():
        mask |= df["Round"].astype(str) == q
    return df[mask].head(limit)


def _enrich_fixture_record(rec: dict[str, Any]) -> dict[str, Any]:
    home = rec.get("HomeTeam", "")
    rec["stadium_image"] = team_stadium_image(home)
    rec["stadium"] = rec.get("stadium") or team_stadium(home)
    return rec


def _season_played(season: str) -> pd.DataFrame:
    all_feats = paths.processed_dir / "match_features_all.parquet"
    if not all_feats.exists():
        return pd.DataFrame()
    df = load_parquet(all_feats)
    mask = (df["season"].astype(str) == season) & (df["played"] == True)  # noqa: E712
    return df[mask].sort_values("Date").reset_index(drop=True)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "templates" / "index.html")


@app.get("/match")
def match_page() -> FileResponse:
    return FileResponse(WEB_DIR / "templates" / "match.html")


@app.get("/team")
def team_page() -> FileResponse:
    return FileResponse(WEB_DIR / "templates" / "team.html")


@app.get("/player")
def player_page() -> FileResponse:
    return FileResponse(WEB_DIR / "templates" / "player.html")


@app.get("/api/config")
def api_config() -> dict[str, str]:
    code = PREDICT_SEASON
    y1, y2 = int(code[:2]), int(code[2:])
    label = f"20{y1}–{y2}"
    return {"predict_season": code, "season_label": label}


@app.get("/api/status")
def status() -> dict[str, Any]:
    files = {
        "played_features": (paths.processed_dir / "match_features_played.parquet").exists(),
        "upcoming_features": (paths.processed_dir / "match_features_upcoming.parquet").exists(),
        "predictions": (paths.processed_dir / "predictions_upcoming.parquet").exists(),
        "model": (paths.models_dir / "pl_ftr_logreg.pkl").exists(),
        "report": (paths.models_dir / "pl_ftr_logreg.report.json").exists(),
    }
    return {
        "ready": all(files.values()),
        "files": files,
        "predict_season": PREDICT_SEASON,
    }


@app.get("/api/training-manifest")
def training_manifest() -> dict[str, Any]:
    path = paths.processed_dir / "training_manifest.json"
    if not path.exists():
        raise HTTPException(404, "Training manifest not found. Run the pipeline first.")
    return json.loads(path.read_text())


@app.get("/api/methodology")
def methodology() -> dict[str, Any]:
    return {
        "engine": "AdvancedFootballSimulator",
        "layers": [
            "Feature engineering: player capabilities, health, chemistry, manager-squad fit",
            "Dixon-Coles Poisson match engine (λ/μ from composite attack/defence + H2H)",
            "Monte Carlo season simulation (5,000+ iterations)",
        ],
        "training_seasons": TRAIN_SEASONS,
        "predict_season": PREDICT_SEASON,
        "training_data_source": "football-data.co.uk (E0 Premier League CSVs)",
        "fixture_source": "Official 2026/27 fixture release via fixturedownload.com (mirrors premierleague.com)",
        "squad_source": "Transfermarkt — squad market values, player list, net transfer spend",
        "features_used": [
            "Player capabilities (0–1) from market values, top-11 starting XI",
            "Live player health with non-linear penalty below 80% (health²)",
            "Player-player chemistry from starting-XI capability variance",
            "Manager-player chemistry from 10-year manager skill ratings",
            "H2H goal-differential modifier with time decay (10 seasons)",
            "Position-weighted composite attack and defence vectors",
            "Dixon-Coles log-linear Poisson rates with home advantage",
        ],
        "does_not_use": [
            "scikit-learn / xgboost for match prediction (legacy model kept for accuracy reporting only)",
            "Injuries unless player health is set below 1.0",
            "Market betting odds",
        ],
        "how_predictions_update": (
            "Re-run python -m src.predict.simulate_season after matchdays. "
            "H2H records and squad data refresh; Monte Carlo re-simulates the full season."
        ),
        "manager_adjustments": MANAGER_BOOST,
        "manager_notes": MANAGER_NOTES,
    }


@app.get("/api/teams")
def teams_api() -> dict[str, Any]:
    from src.teams_meta import TEAM_META
    return {name: team_info(name) for name in TEAM_META}


@app.get("/api/teams/{team}/squad")
def team_squad(team: str) -> dict[str, Any]:
    data = load_squad_data(PREDICT_SEASON).get(team, {})
    if not data:
        raise HTTPException(404, f"Squad data not found for {team}")
    return {
        "team": team,
        "market_value_m": data.get("market_value_m"),
        "net_spend_m": data.get("net_spend_m"),
        "squad_boost": data.get("squad_boost"),
        "players": data.get("players", []),
    }


@app.get("/api/teams/{team}/profile")
def team_profile_api(team: str) -> dict[str, Any]:
    from src.team_profile import team_profile

    try:
        return team_profile(team)
    except Exception as exc:
        raise HTTPException(404, f"Team profile not found for {team}: {exc}") from exc


@app.get("/api/players/profile")
def player_profile_api(team: str, name: str) -> dict[str, Any]:
    from src.player_profile import player_profile

    try:
        return player_profile(team, name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/fixture")
def fixture_detail(home: str, away: str, date: str = "") -> dict[str, Any]:
    row = _find_fixture(home, away, date)
    if row is None:
        raise HTTPException(404, "Fixture not found.")
    rec = _df_to_records(pd.DataFrame([row]))[0]
    return _enrich_fixture_record(rec)


@app.get("/api/matches/search")
def search_matches(q: str = "", limit: int = 25) -> dict[str, Any]:
    df = _load_all_fixtures()
    if df.empty:
        raise HTTPException(404, "Fixtures not found. Run the pipeline first.")
    limit = max(1, min(int(limit), 50))
    hits = _search_fixtures(df, q, limit=limit)
    records = [_enrich_fixture_record(r) for r in _df_to_records(hits)]
    return {"query": q, "count": len(records), "matches": records}


@app.get("/api/fixture/insights")
def fixture_insights_api(home: str, away: str, date: str = "", recent_n: int = 5) -> dict[str, Any]:
    """
    Rich match insights for the match detail page:
    xG bars, scoreline heatmap, recent form, confidence, and short explanation blocks.
    """
    rec = fixture_detail(home=home, away=away, date=date)
    from src.predict.fixture_insights import fixture_insights

    return fixture_insights(rec, recent_n=int(recent_n))


@app.get("/api/report")
def report() -> dict[str, Any]:
    data = _load_json(paths.models_dir / "pl_ftr_logreg.report.json")
    if not data:
        raise HTTPException(404, "Training report not found. Run the pipeline first.")
    return data


@app.get("/api/predictions/upcoming")
def upcoming_predictions() -> list[dict[str, Any]]:
    path = paths.processed_dir / "predictions_upcoming.parquet"
    if not path.exists():
        raise HTTPException(404, "Predictions not found. Run the pipeline first.")
    df = load_parquet(path).sort_values("Date")
    records = [_enrich_fixture_record(r) for r in _df_to_records(df)]
    return records


@app.get("/api/matches/season/{season}")
def season_matches(season: str) -> dict[str, Any]:
    played = _season_played(season)
    preds_path = paths.processed_dir / "predictions_upcoming.parquet"
    upcoming = load_parquet(preds_path) if preds_path.exists() else pd.DataFrame()
    model_path = paths.models_dir / "pl_ftr_logreg.pkl"

    played_with_preds: list[dict[str, Any]] = []
    accuracy: float | None = None

    if len(played) > 0 and model_path.exists():
        model = joblib.load(model_path)
        X = played[FEATURE_COLS].astype(float)
        proba = model.predict_proba(X)
        pred = np.argmax(proba, axis=1)
        enriched = played.copy()
        enriched["p_home"] = proba[:, 0]
        enriched["p_draw"] = proba[:, 1]
        enriched["p_away"] = proba[:, 2]
        enriched["pred_ftr"] = pd.Series(pred).map({0: "H", 1: "D", 2: "A"})
        enriched["correct"] = enriched["pred_ftr"] == enriched["FTR"]
        accuracy = float(enriched["correct"].mean())
        played_with_preds = _df_to_records(enriched)

    return {
        "season": season,
        "played": played_with_preds,
        "upcoming_count": int(len(upcoming)),
        "played_count": int(len(played)),
        "accuracy": accuracy,
    }


@app.get("/api/monte-carlo")
def monte_carlo_standings() -> list[dict[str, Any]]:
    path = paths.processed_dir / "monte_carlo_standings.parquet"
    if not path.exists():
        raise HTTPException(404, "Monte Carlo standings not found. Run simulate_season first.")
    df = load_parquet(path)
    return _df_to_records(df)


@app.get("/api/standings")
def standings() -> list[dict[str, Any]]:
    mc_path = paths.processed_dir / "monte_carlo_standings.parquet"
    if mc_path.exists():
        from src.predict.simulate_season import monte_carlo_to_standings
        mc = load_parquet(mc_path)
        table = monte_carlo_to_standings(mc)
        return _df_to_records(table)

    sim_path = paths.processed_dir / "season_simulation.parquet"
    if not sim_path.exists():
        raise HTTPException(404, "Season simulation not found. Run the pipeline first.")
    sim = load_parquet(sim_path)
    table = build_standings_from_simulation(sim)
    return _df_to_records(table)


@app.get("/api/accuracy/recent")
def recent_accuracy(n: int = 100) -> dict[str, Any]:
    feat_path = paths.processed_dir / "match_features_played.parquet"
    model_path = paths.models_dir / "pl_ftr_logreg.pkl"
    if not feat_path.exists() or not model_path.exists():
        raise HTTPException(404, "Model or features missing.")

    df = load_parquet(feat_path).sort_values("Date").tail(n)
    model = joblib.load(model_path)
    X = df[FEATURE_COLS].astype(float)
    proba = model.predict_proba(X)
    pred = np.argmax(proba, axis=1)
    pred_ftr = pd.Series(pred).map({0: "H", 1: "D", 2: "A"})
    acc = float((pred_ftr == df["FTR"]).mean())

    by_outcome: dict[str, float] = {}
    for label, code in [("Home wins", "H"), ("Draws", "D"), ("Away wins", "A")]:
        subset = df[df["FTR"] == code]
        if len(subset) > 0:
            p = np.argmax(model.predict_proba(subset[FEATURE_COLS].astype(float)), axis=1)
            by_outcome[label] = float((pd.Series(p).map({0: "H", 1: "D", 2: "A"}) == code).mean())

    return {"n": int(len(df)), "accuracy": acc, "by_outcome": by_outcome}
