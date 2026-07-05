from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

from src.config import LEAGUE_CODE, get_paths


@dataclass(frozen=True)
class DownloadedFile:
    season: str
    path: Path
    url: str


def season_to_url(season: str, league_code: str = LEAGUE_CODE) -> str:
    """
    football-data.co.uk historical season URL pattern:
      https://www.football-data.co.uk/mmz4281/{season}/{league}.csv

    Season format is usually like "2324" for 2023-24.
    """
    return f"https://www.football-data.co.uk/mmz4281/{season}/{league_code}.csv"


def download(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def save_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def download_seasons(seasons: Iterable[str]) -> list[DownloadedFile]:
    paths = get_paths()
    out: list[DownloadedFile] = []
    for s in seasons:
        url = season_to_url(s)
        target = paths.raw_dir / f"pl_{s}.csv"
        content = download(url)
        save_bytes(target, content)
        out.append(DownloadedFile(season=s, path=target, url=url))
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download Premier League CSV seasons.")
    p.add_argument(
        "--seasons",
        nargs="+",
        required=True,
        help="Season codes like 2324 (for 2023-24) in football-data.co.uk format.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    files = download_seasons(args.seasons)
    for f in files:
        print(f"Downloaded {f.season}: {f.path} from {f.url}")


if __name__ == "__main__":
    main()

