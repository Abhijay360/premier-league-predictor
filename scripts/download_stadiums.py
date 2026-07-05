"""Download real stadium photos locally (Unsplash, free license)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.teams_meta import LOGO_SLUG

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/*,*/*",
}

# One consistent wide stadium photo — lit stands, crowd, pitch (same look on every card)
STADIUM_PHOTO_URL = (
    "https://images.unsplash.com/photo-1731312084255-6b38e3ea2484"
    "?w=1400&h=520&fit=crop&crop=top&q=88&auto=format"
)


def download_stadium_photos(out_dir: Path, *, force: bool = False) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    for team, slug in LOGO_SLUG.items():
        dest = out_dir / f"{slug}.jpg"
        if not force and dest.exists() and dest.stat().st_size > 50_000:
            ok += 1
            continue
        try:
            r = requests.get(STADIUM_PHOTO_URL, headers=HEADERS, timeout=45)
            if r.status_code == 200 and len(r.content) > 40_000:
                dest.write_bytes(r.content)
                ok += 1
                print(f"  ✓ {team}")
            else:
                print(f"  ✗ {team} (HTTP {r.status_code})")
        except Exception as e:
            print(f"  ✗ {team}: {e}")
        time.sleep(0.15)
    return ok


def main() -> None:
    p = argparse.ArgumentParser(description="Download stadium photos to web/static/stadiums/")
    p.add_argument("--out", default="web/static/stadiums")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    print("Downloading consistent stadium photos…")
    n = download_stadium_photos(root / args.out, force=args.force)
    print(f"Done: {n}/{len(LOGO_SLUG)} stadium photos ready.")


if __name__ == "__main__":
    main()
