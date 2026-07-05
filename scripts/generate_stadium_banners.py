"""Generate local stadium banner SVGs (no external image dependencies)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.teams_meta import LOGO_SLUG, STADIUM_META

TEAM_COLORS: dict[str, tuple[str, str]] = {
    "Arsenal": ("#EF0107", "#063672"),
    "Aston Villa": ("#670E36", "#95BFE5"),
    "Bournemouth": ("#DA291C", "#000000"),
    "Brentford": ("#E30613", "#FFD700"),
    "Brighton": ("#0057B8", "#FFCD00"),
    "Chelsea": ("#034694", "#001489"),
    "Crystal Palace": ("#1B458F", "#C4122E"),
    "Everton": ("#003399", "#FFFFFF"),
    "Fulham": ("#000000", "#CC0000"),
    "Leeds": ("#FFCD00", "#1D428A"),
    "Liverpool": ("#C8102E", "#00B2A9"),
    "Man City": ("#6CABDD", "#1C2C5B"),
    "Man United": ("#DA291C", "#FBE122"),
    "Newcastle": ("#241F20", "#FFFFFF"),
    "Nott'm Forest": ("#DD0000", "#FFFFFF"),
    "Sunderland": ("#EB172B", "#211747"),
    "Tottenham": ("#132257", "#FFFFFF"),
    "West Ham": ("#7A263A", "#1BB1E7"),
    "Wolves": ("#FDB913", "#231F20"),
    "Coventry": ("#69BE28", "#0070C0"),
    "Hull": ("#000000", "#F7A600"),
    "Ipswich": ("#003399", "#FFFFFF"),
}


def _svg(slug: str, team: str, stadium: str, city: str, c1: str, c2: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="800" height="300" fill="url(#g)"/>
  <rect width="800" height="300" fill="#0b0f1a" opacity="0.35"/>
  <text x="40" y="200" fill="#ffffff" font-family="Inter,Arial,sans-serif" font-size="28" font-weight="700">{stadium}</text>
  <text x="40" y="235" fill="#cbd5e1" font-family="Inter,Arial,sans-serif" font-size="18">{city} · {team}</text>
</svg>"""


def generate_stadium_banners(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for team, slug in LOGO_SLUG.items():
        meta = STADIUM_META.get(team, {})
        c1, c2 = TEAM_COLORS.get(team, ("#1e293b", "#334155"))
        svg = _svg(slug, team, meta.get("stadium", "Home Ground"), meta.get("city", ""), c1, c2)
        (out_dir / f"{slug}.svg").write_text(svg)
        n += 1
    return n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="web/static/stadiums")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    n = generate_stadium_banners(root / args.out)
    print(f"Generated {n} stadium banners.")


if __name__ == "__main__":
    main()
