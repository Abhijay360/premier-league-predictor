"""Map official fixture list team names to football-data.co.uk conventions."""

from __future__ import annotations

# Official PL / fixturedownload name -> football-data.co.uk HomeTeam/AwayTeam
OFFICIAL_TO_FOOTBALL_DATA: dict[str, str] = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "Bournemouth",
    "AFC Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds": "Leeds",
    "Leeds United": "Leeds",
    "Leicester": "Leicester",
    "Leicester City": "Leicester",
    "Liverpool": "Liverpool",
    "Man City": "Man City",
    "Manchester City": "Man City",
    "Man Utd": "Man United",
    "Manchester United": "Man United",
    "Newcastle": "Newcastle",
    "Newcastle United": "Newcastle",
    "Nott'm Forest": "Nott'm Forest",
    "Nottingham Forest": "Nott'm Forest",
    "Southampton": "Southampton",
    "Spurs": "Tottenham",
    "Tottenham": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "West Ham": "West Ham",
    "West Ham United": "West Ham",
    "Wolves": "Wolves",
    "Wolverhampton Wanderers": "Wolves",
  # Promoted / historical names present in official lists
    "Coventry": "Coventry",
    "Coventry City": "Coventry",
    "Hull": "Hull",
    "Hull City": "Hull",
    "Ipswich": "Ipswich",
    "Ipswich Town": "Ipswich",
    "Sunderland": "Sunderland",
}


def normalize_team(name: str) -> str:
    name = name.strip()
    if name in OFFICIAL_TO_FOOTBALL_DATA:
        return OFFICIAL_TO_FOOTBALL_DATA[name]
    raise ValueError(f"Unknown team name: {name!r}. Add mapping in src/teams.py")
