"""Fetch Transfermarkt player careers + trophies for every squad player."""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.config import PREDICT_SEASON, get_paths
from src.ingest.fetch_squad_data import HEADERS, load_squad_data

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _sleep(seconds: float = 0.15) -> None:
    time.sleep(seconds)


def _get(url: str, *, json_mode: bool = False, timeout: int = 45) -> Any:
    headers = dict(HEADERS)
    if json_mode:
        headers["Accept"] = "application/json, text/plain, */*"
    for attempt in range(3):
        try:
            # Per-request (thread-safe) rather than shared Session
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json() if json_mode else r.text
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def _season_label(raw: str) -> str:
    raw = (raw or "").strip()
    if re.fullmatch(r"\d{2}/\d{2}", raw):
        a, b = raw.split("/")
        return f"20{a}-{b}"
    return raw


COMP_NAMES: dict[str, str] = {
    "GB1": "Premier League",
    "FAC": "FA Cup",
    "CGB": "EFL Cup",
    "GBCS": "Community Shield",
    "CL": "Champions League",
    "CLQ": "Champions League Qualifying",
    "EL": "Europa League",
    "ELQ": "Europa League Qualifying",
    "ECL": "Conference League",
    "ECLQ": "Conference League Qualifying",
    "KLUB": "Club World Cup",
    "USC": "UEFA Super Cup",
    "FIWC": "FIFA Club World Cup",
    "WM": "World Cup",
    "EM": "European Championship",
    "COSA": "Copa América",
    "NL1": "Nations League",
}


def photo_url_for(tm_player_id: int | str) -> str:
    return f"https://tmssl.akamaized.net/images/portrait/header/{tm_player_id}.png"


def club_id_map_from_transfers(transfers: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for t in transfers or []:
        for side in ("from", "to"):
            club = t.get(side) or {}
            name = (club.get("clubName") or "").strip()
            href = club.get("href") or ""
            m = re.search(r"/verein/(\d+)", href)
            if m and name:
                mapping[m.group(1)] = name
    return mapping


def squad_club_id_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for team, data in load_squad_data().items():
        tm_id = data.get("tm_id")
        if tm_id is not None:
            mapping[str(tm_id)] = team
    return mapping


def aggregate_season_stats(
    performance: list[dict],
    club_names: dict[str, str] | None = None,
    *,
    include_national: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Aggregate TM match performances into season/competition rows + career totals."""
    club_names = club_names or {}
    buckets: dict[tuple, dict[str, Any]] = {}
    totals = {"apps": 0, "goals": 0, "assists": 0, "minutes": 0, "starts": 0}

    for g in performance or []:
        gi = g.get("gameInformation") or {}
        if gi.get("isNationalGame") and not include_national:
            continue
        st = g.get("statistics") or {}
        gen = st.get("generalStatistics") or {}
        if gen.get("participationState") != "played":
            continue

        season_raw = (gi.get("season") or {}).get("nonCyclicalName") or str(gi.get("seasonId") or "")
        season = _season_label(season_raw)
        comp_id = str(gi.get("competitionId") or "")
        club_id = str(
            gen.get("primaryClubId")
            or ((g.get("clubsInformation") or {}).get("club") or {}).get("clubId")
            or ""
        )
        key = (season, comp_id, club_id)
        if key not in buckets:
            buckets[key] = {
                "season": season,
                "competition": COMP_NAMES.get(comp_id, comp_id or "—"),
                "competition_id": comp_id,
                "club": club_names.get(club_id, f"Club {club_id}" if club_id else "—"),
                "club_id": club_id,
                "apps": 0,
                "goals": 0,
                "assists": 0,
                "minutes": 0,
                "starts": 0,
            }

        gs = st.get("goalStatistics") or {}
        mins = st.get("playingTimeStatistics") or {}
        goals = int(gs.get("goalsScoredTotalOfficial") or gs.get("goalsScoredTotal") or 0)
        assists = int(gs.get("assistsOfficial") or gs.get("assists") or 0)
        minutes = int(mins.get("playedMinutes") or 0)
        started = bool(mins.get("isStarting"))

        buckets[key]["apps"] += 1
        buckets[key]["goals"] += goals
        buckets[key]["assists"] += assists
        buckets[key]["minutes"] += minutes
        buckets[key]["starts"] += int(started)

        totals["apps"] += 1
        totals["goals"] += goals
        totals["assists"] += assists
        totals["minutes"] += minutes
        totals["starts"] += int(started)

    def _season_sort_key(season: str) -> tuple:
        m = re.match(r"(\d{4})", season or "")
        return (int(m.group(1)) if m else 0, season)

    rows = sorted(
        buckets.values(),
        key=lambda r: (_season_sort_key(r["season"]), r["competition"], r["club"]),
        reverse=True,
    )
    return rows, totals


def fetch_player_stats(tm_player_id: int, club_names: dict[str, str] | None = None) -> dict[str, Any]:
    payload = _get(
        f"https://www.transfermarkt.com/ceapi/performance-game/{tm_player_id}",
        json_mode=True,
        timeout=90,
    )
    _sleep(0.1)
    performance = []
    if isinstance(payload, dict):
        performance = (payload.get("data") or {}).get("performance") or []
    season_stats, career_totals = aggregate_season_stats(performance, club_names)
    return {
        "photo_url": photo_url_for(tm_player_id),
        "season_stats": season_stats[:40],
        "career_totals": career_totals,
        "stats_fetched": True,
    }


def career_from_transfers(transfers: list[dict]) -> list[dict[str, str]]:
    """Build chronological club stints from TM transfer history (newest first)."""
    clubs: list[dict[str, str]] = []
    for t in reversed(transfers or []):
        to_club = ((t.get("to") or {}).get("clubName") or "").strip()
        if not to_club or to_club.lower() in {"retired", "without club", "career break"}:
            continue
        date = (t.get("date") or "").strip()
        year = date.split("/")[-1] if date else (t.get("season") or "")
        if year and "/" in str(year):
            year = "20" + str(year).split("/")[0]
        if clubs and clubs[-1]["club"] == to_club:
            continue
        if clubs:
            clubs[-1]["to"] = year or clubs[-1]["to"]
        clubs.append({"club": to_club, "from": year or "—", "to": "present"})
    return clubs


def parse_trophies(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    trophies: list[dict[str, Any]] = []
    for box in soup.select("div.box"):
        h2 = box.select_one("h2")
        if not h2:
            continue
        title = h2.get_text(" ", strip=True)
        if not title or title.lower().startswith("all titles"):
            continue
        m = re.match(r"(\d+)x\s+(.+)", title)
        if not m:
            continue
        count = int(m.group(1))
        competition = m.group(2).strip()
        entries: list[dict[str, str]] = []
        for row in box.select("table.auflistung tr"):
            season_el = row.select_one("td.erfolg_table_saison")
            club_el = row.select_one("td a[title]")
            if not season_el:
                continue
            season = _season_label(season_el.get_text(strip=True))
            club = (club_el.get("title") if club_el else "") or ""
            if not club:
                links = [a.get_text(strip=True) for a in row.select("a") if a.get_text(strip=True)]
                club = links[-1] if links else ""
            entries.append({"season": season, "club": club})
        if entries:
            for e in entries:
                trophies.append({
                    "competition": competition,
                    "season": e["season"],
                    "club": e["club"],
                    "label": f"{competition} {e['season']}".strip(),
                })
        else:
            trophies.append({
                "competition": competition,
                "season": "",
                "club": "",
                "label": f"{count}× {competition}",
                "count": count,
            })
    return trophies


def season_summary_from_career(career: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Lightweight season timeline when detailed apps/goals are unavailable."""
    rows: list[dict[str, Any]] = []
    for stint in reversed(career):
        start = stint.get("from") or ""
        end = stint.get("to") or ""
        if not start or start == "—":
            continue
        label = f"{start}–{end}" if end and end != "present" else f"{start}–present"
        rows.append({
            "season": label,
            "club": stint["club"],
            "competition": "Career stint",
            "apps": None,
            "goals": None,
        })
    return rows[:12]


def fetch_player_detail(tm_player_id: int, tm_player_slug: str = "", *, with_stats: bool = True) -> dict[str, Any]:
    slug = tm_player_slug or "spieler"
    transfers_payload = _get(
        f"https://www.transfermarkt.com/ceapi/transferHistory/list/{tm_player_id}",
        json_mode=True,
    )
    _sleep()
    erfolge_html = _get(
        f"https://www.transfermarkt.com/{slug}/erfolge/spieler/{tm_player_id}",
    )
    _sleep()

    transfers = transfers_payload.get("transfers", []) if isinstance(transfers_payload, dict) else []
    career = career_from_transfers(transfers)
    trophies = parse_trophies(erfolge_html or "")
    club_names = {**squad_club_id_map(), **club_id_map_from_transfers(transfers)}
    out: dict[str, Any] = {
        "tm_player_id": tm_player_id,
        "tm_player_slug": slug,
        "photo_url": photo_url_for(tm_player_id),
        "career": career,
        "trophies": trophies,
        "club_id_map": club_names,
        "season_stats": season_summary_from_career(career),
        "career_totals": {"apps": 0, "goals": 0, "assists": 0, "minutes": 0, "starts": 0},
        "stats_fetched": False,
        "source": "transfermarkt.com",
    }
    if with_stats:
        try:
            out.update(fetch_player_stats(tm_player_id, club_names))
        except Exception as exc:
            out["stats_error"] = str(exc)
    return out


def enrich_player_stats(
    season: str = PREDICT_SEASON,
    *,
    limit: int | None = None,
    resume: bool = True,
    workers: int = 6,
) -> Path:
    """Backfill photos + goals/assists for existing profiles."""
    cache = load_profiles(season)
    cache.setdefault("players", {})
    base_clubs = squad_club_id_map()

    pending: list[tuple[str, dict]] = []
    skipped = 0
    for key, row in cache["players"].items():
        if resume and row.get("stats_fetched") and row.get("photo_url"):
            skipped += 1
            continue
        tm_id = row.get("tm_player_id")
        if not tm_id:
            row["photo_url"] = None
            row["stats_fetched"] = False
            continue
        pending.append((key, row))
    if limit is not None:
        pending = pending[:limit]

    print(f"Enriching stats/photos for {len(pending)} players ({skipped} already done)", flush=True)
    done = failed = 0

    def _job(item: tuple[str, dict]) -> tuple[str, dict]:
        key, row = item
        tm_id = int(row["tm_player_id"])
        club_names = {**base_clubs, **(row.get("club_id_map") or {})}
        # Refresh club map from transfers if thin
        if len(club_names) < 3:
            try:
                transfers_payload = _get(
                    f"https://www.transfermarkt.com/ceapi/transferHistory/list/{tm_id}",
                    json_mode=True,
                )
                transfers = transfers_payload.get("transfers", []) if isinstance(transfers_payload, dict) else []
                club_names.update(club_id_map_from_transfers(transfers))
                row["club_id_map"] = club_names
            except Exception:
                pass
        stats = fetch_player_stats(tm_id, club_names)
        row.update(stats)
        return key, row

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, item): item for item in pending}
        for fut in as_completed(futures):
            key, row = futures[fut]
            try:
                k, updated = fut.result()
                cache["players"][k] = updated
                done += 1
            except Exception as exc:
                failed += 1
                row["stats_error"] = str(exc)
                row["photo_url"] = photo_url_for(row["tm_player_id"]) if row.get("tm_player_id") else None
                cache["players"][key] = row
                print(f"  fail {row.get('team')} {row.get('name')}: {exc}", flush=True)
            if (done + failed) % 15 == 0:
                save_profiles(cache, season)
                print(f"  progress: {done} ok, {failed} failed / {len(pending)}", flush=True)

    cache["stats_fetched_count"] = sum(1 for v in cache["players"].values() if v.get("stats_fetched"))
    path = save_profiles(cache, season)
    print(f"Wrote {path} ({cache['stats_fetched_count']} with stats)", flush=True)
    return path


def profiles_path(season: str = PREDICT_SEASON) -> Path:
    return get_paths().data_dir / "player_profiles" / f"profiles_{season}.json"


def load_profiles(season: str = PREDICT_SEASON) -> dict[str, Any]:
    path = profiles_path(season)
    if not path.exists():
        return {"season": season, "players": {}}
    return json.loads(path.read_text())


def save_profiles(data: dict[str, Any], season: str = PREDICT_SEASON) -> Path:
    path = profiles_path(season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def build_player_profiles(
    season: str = PREDICT_SEASON,
    *,
    limit: int | None = None,
    resume: bool = True,
    workers: int = 6,
) -> Path:
    squads = load_squad_data(season)
    cache = load_profiles(season) if resume else {"season": season, "players": {}}
    cache.setdefault("players", {})
    cache["season"] = season

    jobs: list[tuple[str, dict]] = []
    for team, data in squads.items():
        for p in data.get("players", []):
            jobs.append((team, p))
    if limit is not None:
        jobs = jobs[:limit]

    pending: list[tuple[str, dict, str]] = []
    skipped = 0
    for team, p in jobs:
        tm_id = p.get("tm_player_id")
        key = str(tm_id) if tm_id else f"{team}|{p.get('name', '')}".lower()
        if resume and key in cache["players"] and cache["players"][key].get("fetched"):
            skipped += 1
            continue
        pending.append((team, p, key))

    print(f"Fetching {len(pending)} players ({skipped} already cached), workers={workers}", flush=True)

    done = 0
    failed = 0

    def _job(item: tuple[str, dict, str]) -> tuple[str, dict]:
        team, p, key = item
        base = {
            "name": p.get("name"),
            "team": team,
            "position": p.get("position") or "",
            "age": p.get("age") or "",
            "nationality": p.get("nationality") or "",
            "foot": p.get("foot") or "",
            "joined": p.get("joined") or "",
            "market_value_m": p.get("market_value_m"),
            "tm_player_id": p.get("tm_player_id"),
            "tm_player_slug": p.get("tm_player_slug") or "",
            "career": [],
            "trophies": [],
            "season_stats": [],
            "fetched": False,
        }
        tm_id = p.get("tm_player_id")
        if not tm_id:
            base["summary"] = "Profile limited — Transfermarkt player id missing from squad scrape."
            return key, base
        detail = fetch_player_detail(int(tm_id), p.get("tm_player_slug") or "")
        base.update(detail)
        base["fetched"] = True
        if detail["trophies"]:
            most = detail["trophies"][0]
            base["summary"] = (
                f"{base['name']} — most recent honour: "
                f"{most.get('label') or most.get('competition')}."
            )
        elif detail["career"]:
            clubs = ", ".join(c["club"] for c in detail["career"][-3:])
            base["summary"] = f"{base['name']} career path includes {clubs}."
        return key, base

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, item): item for item in pending}
        for fut in as_completed(futures):
            team, p, key = futures[fut]
            try:
                k, row = fut.result()
                cache["players"][k] = row
                if row.get("fetched"):
                    done += 1
                else:
                    if row.get("fetch_error") or not p.get("tm_player_id"):
                        failed += 1 if row.get("fetch_error") else 0
                        done += 1
            except Exception as exc:
                failed += 1
                cache["players"][key] = {
                    "name": p.get("name"),
                    "team": team,
                    "tm_player_id": p.get("tm_player_id"),
                    "career": [],
                    "trophies": [],
                    "season_stats": [],
                    "fetched": False,
                    "fetch_error": str(exc),
                }
                print(f"  fail {team} {p.get('name')}: {exc}", flush=True)
            if (done + failed) % 15 == 0:
                save_profiles(cache, season)
                print(
                    f"  progress: {done} ok, {failed} failed, {skipped} skipped / {len(jobs)}",
                    flush=True,
                )

    cache["fetched_count"] = sum(1 for v in cache["players"].values() if v.get("fetched"))
    cache["player_count"] = len(cache["players"])
    path = save_profiles(cache, season)
    print(f"Wrote {path} ({cache['fetched_count']} full profiles, {failed} failed)", flush=True)
    return path


def remap_stat_names(season: str = PREDICT_SEASON, *, workers: int = 8) -> Path:
    """Resolve all TM club IDs + competition codes to real names in season stats."""
    from src.ingest.tm_reference import resolve_clubs, resolve_competitions

    cache = load_profiles(season)
    players = cache.get("players", {})

    club_ids: set[str] = set()
    comp_codes: set[str] = set()
    for row in players.values():
        for r in row.get("season_stats") or []:
            if r.get("club_id"):
                club_ids.add(str(r["club_id"]))
            if r.get("competition_id"):
                comp_codes.add(str(r["competition_id"]))

    print(f"Resolving {len(club_ids)} clubs and {len(comp_codes)} competitions…", flush=True)
    club_names = resolve_clubs(sorted(club_ids), workers=workers)
    comp_names = resolve_competitions(sorted(comp_codes), workers=workers)

    updated = 0
    for row in players.values():
        for r in row.get("season_stats") or []:
            cid = str(r.get("club_id") or "")
            code = str(r.get("competition_id") or "")
            if cid and club_names.get(cid):
                r["club"] = club_names[cid]
            if code and comp_names.get(code):
                r["competition"] = comp_names[code]
            updated += 1

    path = save_profiles(cache, season)
    print(f"Remapped {updated} stat rows → {path}", flush=True)
    return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Transfermarkt careers/trophies for squad players.")
    p.add_argument("--season", default=PREDICT_SEASON)
    p.add_argument("--limit", type=int, default=None, help="Optional cap for testing")
    p.add_argument("--fresh", action="store_true", help="Ignore existing cache")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--stats", action="store_true", help="Backfill photos + goals/assists only")
    p.add_argument("--remap-names", action="store_true", help="Resolve club/competition names in stats")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.remap_names:
        remap_stat_names(args.season, workers=args.workers)
        return
    if args.stats:
        enrich_player_stats(
            args.season,
            limit=args.limit,
            resume=not args.fresh,
            workers=args.workers,
        )
        return
    build_player_profiles(
        args.season,
        limit=args.limit,
        resume=not args.fresh,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
