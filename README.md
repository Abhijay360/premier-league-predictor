# Premier League Predictor

End-to-end Premier League season prediction engine with a live web dashboard.

Predicts the full **2026–27** campaign using 10 seasons of historical results, Transfermarkt squad data, and a custom **Dixon-Coles Poisson + Monte Carlo** simulator.

## Features

- **AdvancedFootballSimulator** — player capabilities, manager chemistry, H2H modifiers, Dixon-Coles goal rates
- **Monte Carlo season simulation** — 5,000 iterations with expected points and 95% confidence intervals
- **10-year backtesting & self-calibration** — automated hyperparameter tuning via `scipy.optimize`
- **Web dashboard** — fixtures, projected table, match detail pages with squads
- **Transfer-aware** — squad market value, top-11 strength, net spend (Spurs/Chelsea etc.)

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/premier-league-predictor.git
cd premier-league-predictor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Download data, train legacy accuracy model, run Monte Carlo predictions
python -m src.pipeline

# Start dashboard
uvicorn web.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000**

Or one command:

```bash
./scripts/launch.sh
```

## Update after each matchday

```bash
source .venv/bin/activate
python -m src.pipeline
```

Refresh the browser. Played results merge from [football-data.co.uk](https://www.football-data.co.uk) when available.

## Backtesting & calibration

```bash
# Synthetic 6-team demo (2016–2025)
python -m src.predict.backtest_calibration

# Real Premier League history
python -m src.predict.backtest_calibration --pl --simulations 500
```

## Tech stack

| Layer | Tools |
|-------|--------|
| Core engine | `numpy`, `pandas`, `scipy` |
| Dashboard | FastAPI, vanilla JS |
| Data | football-data.co.uk, Transfermarkt, fixturedownload.com |
| Legacy | scikit-learn (accuracy reporting only) |

## Project structure

```
premier-league-predictor/
├── src/
│   ├── ingest/              # CSV download, squads, fixtures
│   ├── features/            # Rolling form / Elo (legacy features)
│   ├── predict/
│   │   ├── advanced_simulator.py    # Dixon-Coles + Monte Carlo
│   │   ├── backtest_calibration.py  # 10-year backtest + optimizer
│   │   └── simulate_season.py       # Primary prediction pipeline
│   └── pipeline.py
├── web/                     # FastAPI + dashboard
├── data/                    # Raw CSVs, squads, predictions
└── scripts/launch.sh
```

## Configuration

Edit `src/config.py`:

```python
PREDICT_SEASON = "2627"  # 2026-27
```

## License

MIT
