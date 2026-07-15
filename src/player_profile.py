"""Player profile pages — squad data + Transfermarkt career/trophy cache."""

from __future__ import annotations

import json
import re
from typing import Any

from src.config import PREDICT_SEASON, get_paths
from src.ingest.fetch_squad_data import load_squad_data
from src.teams_meta import team_info


def _parse_age(age_text: str) -> int | None:
    m = re.search(r"\((\d+)\)", age_text or "")
    return int(m.group(1)) if m else None


def _load_enrichment() -> dict[str, dict]:
    path = get_paths().data_dir / "player_enrichment.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _load_tm_profiles(season: str = PREDICT_SEASON) -> dict[str, dict]:
    path = get_paths().data_dir / "player_profiles" / f"profiles_{season}.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return raw.get("players", {})


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _find_player(team: str, name: str) -> dict[str, Any] | None:
    squad = load_squad_data(PREDICT_SEASON).get(team, {})
    players = squad.get("players", [])
    target = _norm_name(name)
    for p in players:
        if _norm_name(p.get("name", "")) == target:
            return dict(p)
    return None


def _lookup_tm_profile(player: dict[str, Any], team: str, profiles: dict[str, dict]) -> dict[str, Any]:
    tm_id = player.get("tm_player_id")
    if tm_id is not None and str(tm_id) in profiles:
        return profiles[str(tm_id)]
    key = f"{team}|{player.get('name', '')}".lower()
    if key in profiles:
        return profiles[key]
    # fallback: match by normalized name
    target = _norm_name(player.get("name", ""))
    for row in profiles.values():
        if _norm_name(row.get("name", "")) == target:
            return row
    return {}


def player_profile(team: str, name: str) -> dict[str, Any]:
    player = _find_player(team, name)
    if not player:
        raise KeyError(f"Player not found: {name} ({team})")

    enrich_all = _load_enrichment()
    enrich = enrich_all.get(_norm_name(name), enrich_all.get(name, {}))
    tm = _lookup_tm_profile(player, team, _load_tm_profiles())

    squad = load_squad_data(PREDICT_SEASON).get(team, {})
    age = _parse_age(str(player.get("age") or tm.get("age") or enrich.get("age") or ""))

    trophies = tm.get("trophies") or enrich.get("trophies") or []
    career = tm.get("career") or enrich.get("career") or []
    season_stats = tm.get("season_stats") if tm.get("stats_fetched") else None
    if not season_stats:
        season_stats = enrich.get("season_stats") or tm.get("season_stats") or []
    season_stats = _resolve_stat_names(season_stats)
    career_totals = tm.get("career_totals") or enrich.get("career_totals") or {}

    position = (
        player.get("position")
        or tm.get("position")
        or enrich.get("position")
        or "—"
    )
    nationality = player.get("nationality") or tm.get("nationality") or enrich.get("nationality")
    foot = player.get("foot") or tm.get("foot") or enrich.get("foot")
    joined = player.get("joined") or tm.get("joined") or enrich.get("joined")
    tm_id = player.get("tm_player_id") or tm.get("tm_player_id") or enrich.get("tm_player_id")
    photo_url = (
        tm.get("photo_url")
        or enrich.get("photo_url")
        or (f"https://tmssl.akamaized.net/images/portrait/header/{tm_id}.png" if tm_id else None)
    )

    summary = enrich.get("summary") or tm.get("summary")
    if not summary and career:
        summary = f"{player.get('name', name)} — {len(career)} clubs in Transfermarkt career history."
    if not summary:
        summary = "Squad data from Transfermarkt."

    return {
        "name": player.get("name", name),
        "team": team,
        "team_info": team_info(team),
        "position": position,
        "age": age,
        "age_raw": player.get("age") or tm.get("age"),
        "market_value_m": player.get("market_value_m"),
        "nationality": nationality,
        "foot": foot,
        "joined": joined,
        "photo_url": photo_url,
        "trophies": trophies,
        "career": career,
        "season_stats": season_stats,
        "career_totals": career_totals,
        "summary": summary,
        "tm_player_id": tm_id,
        "tm_url": (
            enrich.get("tm_url")
            or (
                f"https://www.transfermarkt.com/{tm.get('tm_player_slug', 'spieler')}/profil/spieler/{tm_id}"
                if tm_id
                else None
            )
        ),
        "squad_rank_value": _value_rank(squad.get("players", []), player),
        "data_source": "transfermarkt" if tm.get("fetched") else ("curated" if enrich else "squad"),
        "club_trophies_note": enrich.get("club_trophies_note"),
    }


def _resolve_stat_names(rows: list[dict]) -> list[dict]:
    """Fill in real club/competition names from the reference cache when needed."""
    if not rows:
        return rows
    try:
        from src.ingest.tm_reference import club_name, competition_name
    except Exception:
        return rows
    out = []
    for r in rows:
        r = dict(r)
        club = r.get("club") or ""
        if (not club or club.startswith("Club ")) and r.get("club_id"):
            resolved = club_name(r["club_id"])
            if resolved:
                r["club"] = resolved
        code = str(r.get("competition_id") or "")
        comp = r.get("competition") or ""
        if code and (not comp or comp == code):
            resolved = competition_name(code)
            if resolved:
                r["competition"] = resolved
        out.append(r)
    return out


def _value_rank(players: list[dict], player: dict) -> int | None:
    if not players:
        return None
    ordered = sorted(players, key=lambda p: p.get("market_value_m") or 0, reverse=True)
    for i, p in enumerate(ordered, start=1):
        if p.get("name") == player.get("name"):
            return i
    return None
