#!/usr/bin/env python3
"""
Consolidate the model's single most-likely outcome for EVERY WC2026 match into
one file: date, teams, goals, winner.

Method (scientific basis):
  - WINNER of each match is taken straight from the ensemble Monte-Carlo engine
    (`0.35·Elo(FIFA) + 0.45·xG-Poisson + 0.20·Form`, 20k tournaments over the
    refreshed 2026-roster ratings in data/wc2026.duckdb). Group outcome from the
    modal-path standings; knockout winner from the modal bracket. These are NOT
    altered here.
  - SCORELINE is the most-likely exact scoreline *consistent with that outcome*
    under independent Poisson goal models, after calibrating the engine's
    expected goals to the historical men's World Cup scoring rate (the raw engine
    runs ~1.3 goals/game vs the ~2.75 WC long-run average, so scorelines are
    scaled up to be realistic without changing who wins).

Reads (already produced by simulate_wc2026_duckdb.py):
  results/wc2026-sim-duckdb/modal_bracket.json   (group scores + KO winners)
  results/wc2026-sim-duckdb/per_game.csv         (per-match Poisson lambdas)
  data/wc2026/tournament.json                    (KO dates/venues)

Writes:
  results/wc2026-sim-duckdb/final_results.csv     (the single deliverable)

Usage:
  python3 tools/build_final_results.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from simulate_wc2026_duckdb import NAME_TO_CODE  # noqa: E402

OUT = ROOT / "results" / "wc2026-sim-duckdb"
TJ = ROOT / "data" / "wc2026" / "tournament.json"
NAME = {v: k for k, v in NAME_TO_CODE.items()}

# Calibration target: long-run men's World Cup goals per game (display only —
# scales expected goals to a realistic scoreline scale; never changes a winner).
WC_AVG_GOALS = 2.75

ROUND_LABEL = {"R32": "Round of 32", "R16": "Round of 16", "QF": "Quarter-final",
               "SF": "Semi-final", "FINAL": "Final"}
FIELDS = ["stage", "date", "home_team", "away_team", "score", "winner"]
MAX_G = 9


def nm(code):
    return NAME.get(code, code)


def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def most_likely_score(lam_h, lam_a, outcome):
    """Most probable exact (home, away) scoreline consistent with `outcome`
    ('H' home win, 'A' away win, 'D' draw) under two independent Poissons."""
    best, best_p = (1, 1), -1.0
    for i in range(MAX_G):
        for j in range(MAX_G):
            if outcome == "H" and not i > j:
                continue
            if outcome == "A" and not i < j:
                continue
            if outcome == "D" and i != j:
                continue
            p = _pois(i, lam_h) * _pois(j, lam_a)
            if p > best_p:
                best_p, best = p, (i, j)
    return best


def main():
    modal = json.loads((OUT / "modal_bracket.json").read_text())
    T = json.loads(TJ.read_text())
    per_game = list(csv.DictReader(open(OUT / "per_game.csv")))

    # Goal calibration: scale engine lambdas so mean total goals == WC_AVG_GOALS.
    totals = [float(r["lam_home"]) + float(r["lam_away"]) for r in per_game]
    k = WC_AVG_GOALS / (sum(totals) / len(totals))

    lam = {(r["home"], r["away"]): (float(r["lam_home"]) * k, float(r["lam_away"]) * k)
           for r in per_game}

    ko_meta = {}
    for rk in ("r32", "r16", "quarterfinals", "semifinals", "final", "third_place"):
        for m in T["bracket"].get(rk, []):
            ko_meta[m["id"]] = {"date": m.get("date", "")}

    rows = []

    # ── Group stage: keep the simulation's outcome, recompute a realistic score ──
    for g in modal["group_results"]:
        gh, ga = (int(x) for x in g["score"].split("-"))
        outcome = "H" if gh > ga else ("A" if ga > gh else "D")
        lh, la = lam.get((g["home"], g["away"]), (1.4, 1.4))
        sh, sa = most_likely_score(lh, la, outcome)
        winner = nm(g["home"]) if outcome == "H" else (nm(g["away"]) if outcome == "A" else "Draw")
        rows.append({
            "stage": f"Group {g['group']}", "date": g["date"],
            "home_team": nm(g["home"]), "away_team": nm(g["away"]),
            "score": f"{sh}-{sa}", "winner": winner,
        })

    # ── Knockouts: winner from the bracket; decisive most-likely scoreline ───────
    for kmatch in modal["ko_results"]:
        t1, t2, w = kmatch["t1"], kmatch["t2"], kmatch["winner"]
        outcome = "H" if w == t1 else "A"
        lh, la = lam.get((t1, t2), (1.4, 1.4))
        sh, sa = most_likely_score(lh, la, outcome)
        rows.append({
            "stage": ROUND_LABEL[kmatch["round"]],
            "date": ko_meta.get(kmatch["id"], {}).get("date", ""),
            "home_team": nm(t1), "away_team": nm(t2),
            "score": f"{sh}-{sa}", "winner": nm(w),
        })

    rows.sort(key=lambda r: (r["date"], r["stage"]))

    with open(OUT / "final_results.csv", "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=FIELDS)
        wtr.writeheader()
        wtr.writerows(rows)

    print(f"Saved → {(OUT / 'final_results.csv').relative_to(ROOT)} "
          f"({len(rows)} games, goal-calibration k={k:.2f})")
    print(f"Champion: {nm(modal['champion'])}")


if __name__ == "__main__":
    main()
