"""Scrape squad market values and transfer spend from Transfermarkt."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from src.config import PREDICT_SEASON, get_paths

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Transfermarkt display name -> football-data / our canonical name
TM_TO_CANONICAL: dict[str, str] = {
    "Manchester City": "Man City",
    "Arsenal FC": "Arsenal",
    "Chelsea FC": "Chelsea",
    "Liverpool FC": "Liverpool",
    "Tottenham Hotspur": "Tottenham",
    "Manchester United": "Man United",
    "Brighton & Hove Albion": "Brighton",
    "Newcastle United": "Newcastle",
    "AFC Bournemouth": "Bournemouth",
    "Aston Villa": "Aston Villa",
    "Nottingham Forest": "Nott'm Forest",
    "Crystal Palace": "Crystal Palace",
    "Brentford FC": "Brentford",
    "Everton FC": "Everton",
    "Sunderland AFC": "Sunderland",
    "Leeds United": "Leeds",
    "Fulham FC": "Fulham",
    "Ipswich Town": "Ipswich",
    "Coventry City": "Coventry",
    "Hull City": "Hull",
    "Wolverhampton Wanderers": "Wolves",
    "West Ham United": "West Ham",
}


def parse_market_value(text: str) -> float:
    """Return market value in millions of euros."""
    t = text.replace("€", "").replace(",", "").strip().lower()
    if not t or t == "-":
        return 0.0
    m = re.search(r"([\d\.]+)\s*(bn|m|k|b)?", t)
    if not m:
        return 0.0
    val = float(m.group(1))
    suffix = m.group(2) or "m"
    if suffix in {"bn", "b"}:
        return val * 1000.0
    if suffix == "m":
        return val
    if suffix == "k":
        return val / 1000.0
    return val


def parse_fee(text: str) -> float:
    """Return transfer fee in millions of euros (0 for free/loan/unknown)."""
    t = text.strip().lower()
    if not t or t in {"-", "?"}:
        return 0.0
    if any(x in t for x in ("free", "loan", "end of loan", "unknown", "without")):
        return 0.0
    return parse_market_value(t)


def fetch_pl_clubs() -> list[dict]:
    url = "https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1"
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    table = soup.select_one("table.items")
    if not table:
        raise ValueError("Could not find PL club table on Transfermarkt.")

    clubs = []
    for row in table.select("tbody tr"):
        link = row.select_one("td.hauptlink a")
        if not link:
            continue
        href = link.get("href", "")
        m = re.search(r"/([^/]+)/startseite/verein/(\d+)", href)
        if not m:
            continue
        tm_slug, tm_id = m.group(1), int(m.group(2))
        tm_name = link.get_text(strip=True)
        mv_text = row.select("td")[-1].get_text(strip=True)
        canonical = TM_TO_CANONICAL.get(tm_name, tm_name.replace(" FC", "").replace(" AFC", ""))
        clubs.append({
            "tm_name": tm_name,
            "team": canonical,
            "tm_id": tm_id,
            "tm_slug": tm_slug,
            "market_value_m": parse_market_value(mv_text),
        })
    return clubs


def fetch_net_spend(tm_slug: str, tm_id: int, season: int = 2026) -> tuple[float, float]:
    """Return (spend_in_m, spend_out_m) for a club in a season."""
    url = f"https://www.transfermarkt.com/{tm_slug}/transfers/verein/{tm_id}/saison_id/{season}"
    r = requests.get(url, headers=HEADERS, timeout=45)
    if r.status_code != 200:
        return 0.0, 0.0

    soup = BeautifulSoup(r.text, "lxml")
    spend_in = spend_out = 0.0

    # Arrivals and departures are in separate boxes with h2 headers
    for box in soup.select("div.box"):
        header = box.select_one("h2")
        if not header:
            continue
        h = header.get_text(strip=True).lower()
        is_in = "arrival" in h
        is_out = "departure" in h or "leave" in h
        if not is_in and not is_out:
            continue
        for row in box.select("table tbody tr"):
            fee_cell = row.select_one("td.rechts.hauptlink") or row.select_one("td.rechts")
            if not fee_cell:
                continue
            fee = parse_fee(fee_cell.get_text(strip=True))
            if is_in:
                spend_in += fee
            elif is_out:
                spend_out += fee

    return round(spend_in, 2), round(spend_out, 2)


def fetch_club_players(tm_slug: str, tm_id: int, season: int = 2026) -> list[dict]:
    """Fetch full squad player list from Transfermarkt."""
    url = f"https://www.transfermarkt.com/{tm_slug}/kader/verein/{tm_id}/saison_id/{season}/plus/1"
    r = requests.get(url, headers=HEADERS, timeout=45)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    table = soup.select_one("table.items")
    if not table:
        return []

    players = []
    seen: set[str] = set()
    # Main data rows only — Transfermarkt duplicates each player in a spacer row
    for row in table.select("tbody tr.odd, tbody tr.even"):
        name_el = row.select_one("td.hauptlink a")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name or name in seen:
            continue
        pos_el = row.select_one("td.posrela table tr td")
        pos = pos_el.get_text(strip=True) if pos_el else ""
        tds = row.select("td")
        age = tds[5].get_text(strip=True) if len(tds) > 5 else ""
        mv_el = row.select_one("td.rechts.hauptlink") or row.select_one("td.rechts")
        mv = parse_market_value(mv_el.get_text(strip=True)) if mv_el else 0.0
        seen.add(name)
        players.append({
            "name": name,
            "position": pos,
            "age": age,
            "market_value_m": mv,
        })
    return players


def build_squad_dataset(season: str = PREDICT_SEASON, *, with_players: bool = True) -> dict:
    season_year = 2000 + int(season[:2])  # 2627 -> 2026
    clubs = fetch_pl_clubs()
    club_entries = []
    for c in clubs:
        spend_in, spend_out = fetch_net_spend(c["tm_slug"], c["tm_id"], season=season_year)
        net = round(spend_in - spend_out, 2)
        players: list[dict] = []
        if with_players:
            players = fetch_club_players(c["tm_slug"], c["tm_id"], season=season_year)
        top11 = sorted(players, key=lambda p: p["market_value_m"], reverse=True)[:11]
        top11_value = round(sum(p["market_value_m"] for p in top11), 1)
        club_entries.append({**c, "spend_in_m": spend_in, "spend_out_m": spend_out,
                             "net_spend_m": net, "players": players, "top11_value_m": top11_value,
                             "player_count": len(players)})

    max_mv = max(c["market_value_m"] for c in clubs) if clubs else 1.0
    max_top11 = max((e["top11_value_m"] for e in club_entries), default=1.0) or 1.0

    teams = []
    for c in club_entries:
        mv_norm = c["market_value_m"] / max_mv
        spend_boost = max(-0.3, min(0.3, c["net_spend_m"] / 100.0 * 0.3))
        top11_norm = c["top11_value_m"] / max_top11
        squad_boost = round(0.55 * mv_norm + 0.20 * (0.5 + spend_boost) + 0.25 * top11_norm, 4)
        teams.append({**c, "squad_boost": squad_boost})

    return {
        "season": season,
        "source": "transfermarkt.com",
        "fetched_teams": len(teams),
        "teams": teams,
    }


def save_squad_data(season: str = PREDICT_SEASON) -> Path:
    data = build_squad_dataset(season)
    paths = get_paths()
    out = paths.data_dir / "squads" / f"squad_{season}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    return out


def load_squad_data(season: str = PREDICT_SEASON) -> dict[str, dict]:
    paths = get_paths()
    path = paths.data_dir / "squads" / f"squad_{season}.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {t["team"]: t for t in raw.get("teams", [])}


def load_squad_players(season: str = PREDICT_SEASON) -> dict[str, list[dict]]:
    lookup = load_squad_data(season)
    return {team: data.get("players", []) for team, data in lookup.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch squad values and transfer spend.")
    p.add_argument("--season", default=PREDICT_SEASON)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    path = save_squad_data(args.season)
    data = json.loads(path.read_text())
    print(f"Wrote squad data: {path} ({data['fetched_teams']} teams)")
    for t in sorted(data["teams"], key=lambda x: -x["squad_boost"])[:5]:
        print(f"  {t['team']}: €{t['market_value_m']:.0f}m squad, net spend €{t['net_spend_m']:+.0f}m, boost={t['squad_boost']:.3f}")


if __name__ == "__main__":
    main()
