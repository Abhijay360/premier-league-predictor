"""Download official Premier League fixtures (released fixture list)."""

from __future__ import annotations

import argparse
import re
from html import unescape
from pathlib import Path

import pandas as pd
import requests

from src.config import get_paths
from src.teams import normalize_team

# fixturedownload.com mirrors the official PL fixture release (380 matches).
# Source page: https://fixturedownload.com/results/epl-2026
FIXTURE_URLS: dict[str, str] = {
    "2627": "https://fixturedownload.com/results/epl-2026",
}


def _parse_fixtures_html(html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = re.compile(
        r"<tr>\s*<td>(\d+)</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>"
        r"\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td>([^<]*)</td>",
        re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        round_no, date_time, _venue, home, away, result = m.groups()
        date_part = date_time.strip().split()[0]
        rows.append({
            "Round": round_no,
            "Date": date_part,
            "HomeTeam": normalize_team(unescape(home)),
            "AwayTeam": normalize_team(unescape(away)),
            "Result": unescape(result.strip()) or None,
        })
    return rows


def download_official_fixtures(season: str) -> pd.DataFrame:
    if season not in FIXTURE_URLS:
        raise ValueError(
            f"No official fixture URL for season {season}. "
            f"Add it to FIXTURE_URLS in download_official_fixtures.py"
        )

    url = FIXTURE_URLS[season]
    r = requests.get(url, timeout=60, headers={"User-Agent": "premier-league-predictor/1.0"})
    r.raise_for_status()

    rows = _parse_fixtures_html(r.text)
    if len(rows) != 380:
        raise ValueError(f"Expected 380 fixtures, parsed {len(rows)} from {url}")

    df = pd.DataFrame(rows)
    df["Div"] = "E0"
    df["FTHG"] = pd.NA
    df["FTAG"] = pd.NA
    df["FTR"] = pd.NA

    # If results are present in the feed, populate scores.
    for i, row in df.iterrows():
        res = row.get("Result")
        if res and res != "-" and isinstance(res, str) and "-" in res:
            parts = res.split("-")
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                hg, ag = int(parts[0]), int(parts[1])
                df.at[i, "FTHG"] = hg
                df.at[i, "FTAG"] = ag
                if hg > ag:
                    df.at[i, "FTR"] = "H"
                elif hg < ag:
                    df.at[i, "FTR"] = "A"
                else:
                    df.at[i, "FTR"] = "D"

    return df[["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "Round"]]


def save_official_fixtures(season: str) -> Path:
    df = download_official_fixtures(season)
    paths = get_paths()
    out = paths.raw_dir / f"pl_{season}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download official PL fixture list.")
    p.add_argument("--season", required=True, help="Season code e.g. 2627")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    path = save_official_fixtures(args.season)
    n = len(pd.read_csv(path))
    print(f"Wrote {n} official fixtures to {path}")


if __name__ == "__main__":
    main()
