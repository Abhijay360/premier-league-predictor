"""Resolve Transfermarkt club IDs and competition codes to human names (cached)."""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from src.config import get_paths
from src.ingest.fetch_squad_data import HEADERS

_CLUB_CACHE: dict[str, str] | None = None
_COMP_CACHE: dict[str, str] | None = None


def _ref_dir() -> Path:
    d = get_paths().data_dir / "reference"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clubs_cache_path() -> Path:
    return _ref_dir() / "tm_clubs.json"


def competitions_cache_path() -> Path:
    return _ref_dir() / "tm_competitions.json"


def _load(path: Path) -> dict[str, str]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def load_club_names() -> dict[str, str]:
    global _CLUB_CACHE
    if _CLUB_CACHE is None:
        _CLUB_CACHE = _load(clubs_cache_path())
    return _CLUB_CACHE


def load_competition_names() -> dict[str, str]:
    global _COMP_CACHE
    if _COMP_CACHE is None:
        _COMP_CACHE = _load(competitions_cache_path())
    return _COMP_CACHE


def _get_title(url: str, timeout: int = 30) -> str | None:
    headers = dict(HEADERS)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "lxml")
            return soup.title.get_text(strip=True) if soup.title else None
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _clean_club_title(title: str) -> str:
    name = title.split(" - Club profile")[0]
    name = name.split(" - Vereinsprofil")[0]
    name = re.sub(r"\s*\|\s*Transfermarkt\s*$", "", name)
    name = re.sub(r"\s*\(-\s*\d{4}\)\s*$", "", name)  # defunct marker "(- 2025)"
    return name.strip()


def _clean_competition_title(title: str) -> str:
    name = re.sub(r"\s*\|\s*Transfermarkt\s*$", "", title)
    name = re.sub(r"\s+\d{2}/\d{2}\s*$", "", name)  # trailing "26/27"
    name = re.sub(r"\s+\d{4}\s*$", "", name)  # trailing "2026"
    return name.strip()


def resolve_clubs(club_ids: list[str], *, workers: int = 8, refresh: bool = False) -> dict[str, str]:
    cache = load_club_names()
    todo = [str(c) for c in club_ids if str(c) and (refresh or str(c) not in cache)]
    todo = sorted(set(todo))
    if not todo:
        return cache

    def _job(cid: str) -> tuple[str, str | None]:
        title = _get_title(f"https://www.transfermarkt.com/x/startseite/verein/{cid}")
        return cid, (_clean_club_title(title) if title else None)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, cid): cid for cid in todo}
        for fut in as_completed(futures):
            cid = futures[fut]
            try:
                _, name = fut.result()
            except Exception:
                name = None
            cache[cid] = name or f"Club {cid}"
            done += 1
            if done % 25 == 0:
                clubs_cache_path().write_text(json.dumps(cache, indent=2, ensure_ascii=False))
                print(f"  clubs: {done}/{len(todo)}", flush=True)

    clubs_cache_path().write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    return cache


def resolve_competitions(codes: list[str], *, workers: int = 8, refresh: bool = False) -> dict[str, str]:
    cache = load_competition_names()
    todo = [str(c) for c in codes if str(c) and (refresh or str(c) not in cache)]
    todo = sorted(set(todo))
    if not todo:
        return cache

    def _job(code: str) -> tuple[str, str | None]:
        title = _get_title(f"https://www.transfermarkt.com/x/startseite/wettbewerb/{code}")
        return code, (_clean_competition_title(title) if title else None)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, code): code for code in todo}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                _, name = fut.result()
            except Exception:
                name = None
            cache[code] = name or code
            done += 1
            if done % 25 == 0:
                competitions_cache_path().write_text(json.dumps(cache, indent=2, ensure_ascii=False))
                print(f"  competitions: {done}/{len(todo)}", flush=True)

    competitions_cache_path().write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    return cache


def club_name(club_id: str | int | None) -> str | None:
    if club_id is None or club_id == "":
        return None
    return load_club_names().get(str(club_id))


def competition_name(code: str | None) -> str | None:
    if not code:
        return None
    return load_competition_names().get(str(code))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Resolve TM club/competition names.")
    p.add_argument("--clubs", nargs="*", default=[])
    p.add_argument("--competitions", nargs="*", default=[])
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.clubs:
        print(resolve_clubs(args.clubs))
    if args.competitions:
        print(resolve_competitions(args.competitions))


if __name__ == "__main__":
    main()
