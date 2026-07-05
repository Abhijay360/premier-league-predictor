from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"


def get_paths() -> Paths:
    # src/ -> project root
    root = Path(__file__).resolve().parents[1]
    return Paths(root=root)


LEAGUE_CODE = "E0"  # football-data.co.uk code for Premier League

# Season to predict (2026-27). Update when football-data publishes the CSV.
PREDICT_SEASON = "2627"
# Train on the 10 seasons immediately before the predict season.
TRAIN_SEASONS = [
    "1617", "1718", "1819", "1920", "2021",
    "2122", "2223", "2324", "2425", "2526",
]
