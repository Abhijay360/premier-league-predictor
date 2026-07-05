"""Track per-team form and Elo for feature building and season simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.config import PREDICT_SEASON
from src.ingest.fetch_squad_data import load_squad_data
from src.manager_adjustments import manager_boost
from src.predict.squad_ratings import blend_with_squad, squad_implied_elo, squad_implied_ppg

INITIAL_ELO = 1500.0
HOME_ELO_ADV = 65.0
ELO_K = 20.0
RECENT_WEIGHT = 0.35
ANCHOR_WEIGHT = 0.25  # historical anchor; squad/current-season carries more weight at predict time


@dataclass
class TeamTracker:
    form_window: int = 10
    baseline_window: int = 38
    squad_lookup: dict[str, dict] = field(default_factory=dict)
    use_squad_features: bool = False

    gf: dict[str, list[float]] = field(default_factory=dict)
    ga: dict[str, list[float]] = field(default_factory=dict)
    pts: dict[str, list[float]] = field(default_factory=dict)
    gd: dict[str, list[float]] = field(default_factory=dict)
    elo: dict[str, float] = field(default_factory=dict)
    # Fixed anchor from end of prior season — does not collapse during simulation
    anchor_ppg: dict[str, float] = field(default_factory=dict)
    anchor_elo: dict[str, float] = field(default_factory=dict)

    league_gf: list[float] = field(default_factory=list)
    league_ga: list[float] = field(default_factory=list)
    league_pts: list[float] = field(default_factory=list)

    league_defaults: dict[str, float] = field(default_factory=lambda: {
        "form_games": 0.0,
        "avg_gf": 1.45,
        "avg_ga": 1.45,
        "avg_gd": 0.0,
        "avg_pts": 1.35,
        "win_rate": 0.33,
    })

    def _ensure_team(self, team: str) -> None:
        if team not in self.pts:
            self.pts[team] = []
            self.gf[team] = []
            self.ga[team] = []
            self.gd[team] = []
            self.elo.setdefault(team, INITIAL_ELO)

    def snapshot_anchors(self) -> None:
        """Lock in current strength as season-start anchor for every known team."""
        for team in list(self.pts.keys()):
            stats = self._window_stats(team, self.baseline_window) or self._window_stats(team, self.form_window)
            if stats:
                self.anchor_ppg[team] = stats["avg_pts"]
            elif team not in self.anchor_ppg:
                self.anchor_ppg[team] = self.league_defaults["avg_pts"]
            self.anchor_elo[team] = self.elo.get(team, INITIAL_ELO)

    def _window_stats(self, team: str, window: int) -> dict[str, float] | None:
        self._ensure_team(team)
        k = min(window, len(self.pts[team]))
        if k == 0:
            return None
        pts = np.array(self.pts[team][-k:], dtype=float)
        gf = np.array(self.gf[team][-k:], dtype=float)
        ga = np.array(self.ga[team][-k:], dtype=float)
        gd = np.array(self.gd[team][-k:], dtype=float)
        return {
            "form_games": float(k),
            "avg_gf": float(gf.mean()),
            "avg_ga": float(ga.mean()),
            "avg_gd": float(gd.mean()),
            "avg_pts": float(pts.mean()),
            "win_rate": float((pts == 3.0).mean()),
        }

    def _league_avg(self) -> dict[str, float]:
        if len(self.league_pts) < 50:
            return dict(self.league_defaults)
        gf = np.array(self.league_gf[-500:], dtype=float)
        ga = np.array(self.league_ga[-500:], dtype=float)
        pts = np.array(self.league_pts[-500:], dtype=float)
        return {
            "form_games": 0.0,
            "avg_gf": float(gf.mean()),
            "avg_ga": float(ga.mean()),
            "avg_gd": float((gf - ga).mean()),
            "avg_pts": float(pts.mean()),
            "win_rate": float((pts == 3.0).mean()),
        }

    def summarize(self, team: str) -> dict[str, float]:
        self._ensure_team(team)
        recent = self._window_stats(team, self.form_window)
        baseline = self._window_stats(team, self.baseline_window)

        if recent is None and baseline is None:
            rolling = self._league_avg()
        elif recent is None:
            rolling = baseline  # type: ignore[assignment]
        elif baseline is None:
            rolling = recent
        else:
            w = RECENT_WEIGHT
            rolling = {
                "form_games": recent["form_games"],
                "avg_gf": w * recent["avg_gf"] + (1 - w) * baseline["avg_gf"],
                "avg_ga": w * recent["avg_ga"] + (1 - w) * baseline["avg_ga"],
                "avg_gd": w * recent["avg_gd"] + (1 - w) * baseline["avg_gd"],
                "avg_pts": w * recent["avg_pts"] + (1 - w) * baseline["avg_pts"],
                "win_rate": w * recent["win_rate"] + (1 - w) * baseline["win_rate"],
            }

        if self.use_squad_features:
            sq = self._squad(team)
            mgr = manager_boost(team)
            tm = self.squad_lookup.get(team, {})
            net = float(tm.get("net_spend_m", 0))
            spend_in = float(tm.get("spend_in_m", 0))
            from src.predict.squad_ratings import effective_squad_boost
            eff = effective_squad_boost(sq["squad_boost"], net, spend_in)
            sq_attack = 1.0 + (eff - 0.5) * 0.40
            sq_defence = max(0.85, 1.0 - (eff - 0.5) * 0.15)
            new_gf = rolling["avg_gf"] * sq_attack
            new_ga = max(0.92, rolling["avg_ga"] * sq_defence)
            rolling = {
                **rolling,
                "avg_gf": new_gf,
                "avg_ga": new_ga,
                "avg_gd": new_gf - new_ga,
                "win_rate": min(0.75, rolling["win_rate"] + (eff - 0.5) * 0.28),
            }

        anchor_ppg = self.anchor_ppg.get(team, rolling["avg_pts"])
        aw = ANCHOR_WEIGHT
        avg_pts = aw * anchor_ppg + (1 - aw) * rolling["avg_pts"]
        if self.use_squad_features:
            implied = squad_implied_ppg(sq["squad_boost"], mgr, net, spend_in)
            avg_pts = blend_with_squad(avg_pts, sq["squad_boost"], mgr, net, spend_in)
            anchor_ppg = 0.35 * anchor_ppg + 0.65 * implied
        return {
            "form_games": rolling["form_games"],
            "avg_gf": rolling["avg_gf"],
            "avg_ga": rolling["avg_ga"],
            "avg_gd": rolling["avg_gd"],
            "avg_pts": avg_pts,
            "win_rate": rolling["win_rate"],
            "prior_ppg": anchor_ppg,
        }

    def team_elo(self, team: str) -> float:
        self._ensure_team(team)
        current = self.elo[team]
        anchor = self.anchor_elo.get(team, current)
        return ANCHOR_WEIGHT * anchor + (1 - ANCHOR_WEIGHT) * current

    def _squad(self, team: str) -> dict[str, float]:
        neutral = {
            "squad_value_norm": 350.0 / 1500.0,
            "net_spend_norm": 0.0,
            "squad_boost": 0.5,
        }
        if not self.use_squad_features:
            return neutral
        if not self.squad_lookup:
            self.squad_lookup = load_squad_data(PREDICT_SEASON)
        s = self.squad_lookup.get(team, {})
        mv = float(s.get("market_value_m", 350.0))
        net = float(s.get("net_spend_m", 0.0))
        boost = float(s.get("squad_boost", 0.5))
        return {
            "squad_value_norm": mv / 1500.0,
            "net_spend_norm": net / 100.0,
            "squad_boost": boost,
        }

    def match_features(self, home: str, away: str) -> dict[str, float]:
        home_s = self.summarize(home)
        away_s = self.summarize(away)
        home_sq = self._squad(home)
        away_sq = self._squad(away)
        # Squad + manager quality shifts Elo at prediction time
        sq_elo = 180.0 if self.use_squad_features else 0.0
        home_mgr = manager_boost(home) if self.use_squad_features else 0.0
        away_mgr = manager_boost(away) if self.use_squad_features else 0.0
        if self.use_squad_features:
            home_tm = self.squad_lookup.get(home, {})
            away_tm = self.squad_lookup.get(away, {})
            from src.predict.squad_ratings import effective_squad_boost
            home_eff = effective_squad_boost(
                home_sq["squad_boost"], float(home_tm.get("net_spend_m", 0)), float(home_tm.get("spend_in_m", 0))
            )
            away_eff = effective_squad_boost(
                away_sq["squad_boost"], float(away_tm.get("net_spend_m", 0)), float(away_tm.get("spend_in_m", 0))
            )
            home_elo = squad_implied_elo(home_sq["squad_boost"], home_mgr, float(home_tm.get("net_spend_m", 0)), float(home_tm.get("spend_in_m", 0))) * 0.50 + self.team_elo(home) * 0.50
            away_elo = squad_implied_elo(away_sq["squad_boost"], away_mgr, float(away_tm.get("net_spend_m", 0)), float(away_tm.get("spend_in_m", 0))) * 0.50 + self.team_elo(away) * 0.50
        else:
            home_elo = self.team_elo(home)
            away_elo = self.team_elo(away)
        feat: dict[str, float] = {
            "home_advantage": 1.0,
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_diff": home_elo - away_elo + HOME_ELO_ADV,
            "home_prior_ppg": home_s.get("prior_ppg", home_s["avg_pts"]) if "prior_ppg" in home_s else home_s["avg_pts"],
            "away_prior_ppg": away_s.get("prior_ppg", away_s["avg_pts"]) if "prior_ppg" in away_s else away_s["avg_pts"],
            "home_squad_value_norm": home_sq["squad_value_norm"],
            "away_squad_value_norm": away_sq["squad_value_norm"],
            "home_net_spend_norm": home_sq["net_spend_norm"],
            "away_net_spend_norm": away_sq["net_spend_norm"],
            "home_squad_boost": home_sq["squad_boost"],
            "away_squad_boost": away_sq["squad_boost"],
        }
        for k, v in home_s.items():
            if k != "prior_ppg":
                feat[f"home_{k}"] = v
        for k, v in away_s.items():
            if k != "prior_ppg":
                feat[f"away_{k}"] = v
        return feat

    def is_cold_start(self, team: str) -> bool:
        self._ensure_team(team)
        return len(self.pts[team]) == 0

    def _expected_home_score(self, home: str, away: str) -> float:
        home_elo = self.team_elo(home)
        away_elo = self.team_elo(away)
        return 1.0 / (1.0 + 10 ** ((away_elo - home_elo - HOME_ELO_ADV) / 400.0))

    def update(self, home: str, away: str, fthg: int, ftag: int) -> None:
        self._ensure_team(home)
        self._ensure_team(away)

        if fthg > ftag:
            home_pts, away_pts = 3.0, 0.0
            home_result, away_result = 1.0, 0.0
        elif fthg < ftag:
            home_pts, away_pts = 0.0, 3.0
            home_result, away_result = 0.0, 1.0
        else:
            home_pts, away_pts = 1.0, 1.0
            home_result, away_result = 0.5, 0.5

        expected_home = self._expected_home_score(home, away)
        self.elo[home] += ELO_K * (home_result - expected_home)
        self.elo[away] += ELO_K * ((1 - home_result) - (1 - expected_home))

        for team, gf_v, ga_v, gd_v, pt in [
            (home, float(fthg), float(ftag), float(fthg - ftag), home_pts),
            (away, float(ftag), float(fthg), float(ftag - fthg), away_pts),
        ]:
            self.gf[team].append(gf_v)
            self.ga[team].append(ga_v)
            self.gd[team].append(gd_v)
            self.pts[team].append(pt)

        self.league_gf.extend([float(fthg), float(ftag)])
        self.league_ga.extend([float(ftag), float(fthg)])
        self.league_pts.extend([home_pts, away_pts])
