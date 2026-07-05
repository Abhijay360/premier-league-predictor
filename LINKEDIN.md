# LinkedIn — Premier League Predictor

## Project title (for Experience / Projects section)

**Premier League Predictor** — Football Season Simulation Engine

## One-line headline

Built an end-to-end Premier League prediction engine with Dixon-Coles Poisson modelling, Monte Carlo simulation, and a live FastAPI dashboard.

---

## Short description (≈300 characters — Projects section)

Developed a full-stack football analytics system that predicts the 2026–27 Premier League season. Ingests 10 years of match data and Transfermarkt squad values, runs a custom Dixon-Coles + Monte Carlo simulator (5,000 iterations), and serves projections through a FastAPI web dashboard with fixture-level probabilities and league tables.

---

## Full post (copy-paste for LinkedIn feed)

🏆 **I built a Premier League season predictor from scratch — and it's live.**

What started as a stats project turned into a full end-to-end system:

📊 **Data pipeline**
• 10 seasons of historical results (football-data.co.uk)
• Transfermarkt squad values, transfers & full player squads
• Official 2026–27 fixture list (380 matches)

🧠 **Prediction engine**
• Custom `AdvancedFootballSimulator` — no black-box ML for match outcomes
• Dixon-Coles Poisson model for goal rates (λ/μ)
• Player capability ratings, manager chemistry, H2H modifiers
• Monte Carlo simulation (5,000 runs) → expected points + 95% confidence intervals
• 10-year backtesting with automated hyperparameter calibration (`scipy.optimize`)

🖥️ **Dashboard**
• FastAPI backend + interactive web UI
• Projected league table, upcoming fixtures with H/D/A probabilities
• Match detail pages with squad sheets

**Tech:** Python · NumPy · Pandas · SciPy · FastAPI · Poisson statistics · Monte Carlo methods

The model accounts for summer signings (e.g. Spurs €150m spend, Chelsea under Xabi Alonso) — not just last season's table.

🔗 GitHub: [ADD YOUR REPO URL AFTER PUSH]

#Python #DataScience #SportsAnalytics #MachineLearning #Football #PremierLeague #FastAPI #MonteCarlo #OpenSource

---

## Skills to tag on LinkedIn

Python · Data Analysis · Statistical Modeling · Sports Analytics · FastAPI · NumPy · Pandas · SciPy · Monte Carlo Simulation · Poisson Regression · Web Development · API Development · Data Visualization · ETL

---

## Bullet points (for CV / resume)

- Designed and implemented a **Dixon-Coles Poisson football simulator** with player-level capability ratings, manager chemistry, and head-to-head modifiers
- Built a **Monte Carlo season engine** (5,000 iterations) producing expected points and confidence intervals for all 20 Premier League clubs
- Created a **10-year backtesting & self-calibration pipeline** using `scipy.optimize` to tune hyperparameters against historical RMSE
- Integrated **Transfermarkt** squad data (market values, net spend, player rosters) to adjust projections for summer transfers
- Delivered a **FastAPI dashboard** with fixture predictions, projected standings, and match detail pages
- Ingested and processed **3,800+ historical matches** across 10 seasons with automated ETL from football-data.co.uk

---

## Featured media suggestions

1. Screenshot of the **Projected Table** tab (dark theme dashboard)
2. Screenshot of **Upcoming Fixtures** with probability bars
3. Architecture diagram: Data → Feature Engineering → Dixon-Coles → Monte Carlo → Dashboard

---

## GitHub repo description (for GitHub "About" section)

⚽ Premier League season predictor — Dixon-Coles Poisson + Monte Carlo simulation, Transfermarkt squad data, 10-year backtesting, FastAPI dashboard. Python.

**Topics:** `python` `football` `premier-league` `sports-analytics` `monte-carlo` `poisson` `fastapi` `data-science` `simulation`
