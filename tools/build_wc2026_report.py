#!/usr/bin/env python3
"""
Build the fun, data-backed WC2026 prediction report (REPORT.md).

Reads the simulator's artifacts — probabilities.csv (stage odds), per_game.csv
(per-match 1X2 + character), modal_bracket.json (the most-likely path) — and the
read-only narrative extractors (top players + economics), and writes a readable
group-by-group + knockout + final report.

The engine is unchanged: economics and players are narrative color only. The
report names whatever champion the model produces — no thumb on the scale.

Usage:
  python3 tools/build_wc2026_report.py            # after running the simulator
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lib.wc2026_context import connect, top_players, team_econ  # noqa: E402
from simulate_wc2026_duckdb import NAME_TO_CODE  # noqa: E402

OUT = ROOT / "results" / "wc2026-sim-duckdb"
TJ = ROOT / "data" / "wc2026" / "tournament.json"

CODE_TO_NAME = {code: name for name, code in NAME_TO_CODE.items()}
RUN_SEED = 42
RUN_N = 20000

ROUND_TITLES = {
    "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarter-finals",
    "SF": "Semi-finals", "FINAL": "Final",
}


# ── formatting helpers ──────────────────────────────────────────────────────────
def name(code: str) -> str:
    return CODE_TO_NAME.get(code, code)


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def money(g: float | None) -> str:
    if g is None:
        return "unknown GDP"
    if g >= 1000:
        return f"${g / 1000:.1f}k"
    return f"${g:,.0f}"


def people(p: float | None) -> str:
    if p is None:
        return "unknown population"
    if p >= 1_000_000:
        return f"{p / 1_000_000:.1f}M"
    return f"{p / 1000:.0f}k"


# ── load artifacts ──────────────────────────────────────────────────────────────
def load():
    probs = {}
    with open(OUT / "probabilities.csv") as f:
        for r in csv.DictReader(f):
            probs[r["team"]] = {k: float(v) for k, v in r.items() if k != "team"}
    per_game = list(csv.DictReader(open(OUT / "per_game.csv")))
    modal = json.loads((OUT / "modal_bracket.json").read_text())
    T = json.loads(TJ.read_text())
    return probs, per_game, modal, T


# ── group standings recomputed from the modal scores ────────────────────────────
def group_standings(group_results, group_id, winners, runners_up):
    matches = [m for m in group_results if m["group"] == group_id]
    pts = defaultdict(int); gd = defaultdict(int); gs = defaultdict(int)
    teams = set()
    for m in matches:
        h, a = m["home"], m["away"]; teams.add(h); teams.add(a)
        gh, ga = (int(x) for x in m["score"].split("-"))
        gs[h] += gh; gs[a] += ga
        gd[h] += gh - ga; gd[a] += ga - gh
        if gh > ga: pts[h] += 3
        elif gh < ga: pts[a] += 3
        else: pts[h] += 1; pts[a] += 1
    # Anchor 1st/2nd to the bracket; order the rest by (pts, gd, gs).
    top1, top2 = winners[group_id], runners_up[group_id]
    rest = sorted((t for t in teams if t not in (top1, top2)),
                  key=lambda t: (-pts[t], -gd[t], -gs[t]))
    ordered = [top1, top2] + rest
    return [{"team": t, "pts": pts[t], "gd": gd[t], "gs": gs[t]} for t in ordered]


# ── narrative pieces ────────────────────────────────────────────────────────────
def group_hooks(con, group_id, group_rows, standings):
    """1-2 data-driven, fun observations per group."""
    hooks = []

    # Biggest single-match favorite in the group.
    def fav_p(r):
        return max(float(r["p_home"]), float(r["p_away"]))
    lock = max(group_rows, key=fav_p)
    lp = fav_p(lock)
    fav, dog = (lock["home"], lock["away"]) if float(lock["p_home"]) >= float(lock["p_away"]) \
        else (lock["away"], lock["home"])
    if lp >= 0.55:
        hooks.append(f"The model's surest thing here: **{name(fav)} {pct(lp)}** to beat "
                     f"{name(dog)}.")

    # The powder keg: tightest match, ideally a 3-way split.
    keg = min(group_rows, key=lambda r: abs(float(r["p_home"]) - float(r["p_away"])))
    if abs(float(keg["p_home"]) - float(keg["p_away"])) < 0.08:
        tag = "a genuine three-way coin-flip" if keg["confidence_band"] == "3-way-split" \
            else "too close to call"
        hooks.append(f"**{name(keg['home'])} vs {name(keg['away'])}** is {tag} "
                     f"({pct(float(keg['p_home']))} / {pct(float(keg['p_draw']))} / "
                     f"{pct(float(keg['p_away']))}).")

    # David-vs-Goliath: smallest nation by population in the group.
    econs = [(t["team"], team_econ(con, t["team"])) for t in standings]
    econs = [(c, e) for c, e in econs if e and e.population]
    if econs:
        smallest = min(econs, key=lambda ce: ce[1].population)
        code, e = smallest
        biggest = max(econs, key=lambda ce: ce[1].population)
        if biggest[1].population and e.population and biggest[1].population > e.population * 5:
            ratio = biggest[1].population / e.population
            hooks.append(f"David-watch: **{name(code)}** ({people(e.population)} people, "
                         f"{money(e.gdp_per_capita_usd)}/capita) is dwarfed by "
                         f"{name(biggest[0])} — ~{ratio:.0f}× the population.")
    return hooks


def group_section(con, T, per_game, modal):
    lines = ["## The 12 groups — what the model sees\n"]
    pg_by_group = defaultdict(list)
    for r in per_game:
        if r["stage"] == "group":
            pg_by_group[r["group"]].append(r)

    advancing_thirds = set(modal["thirds"].values())

    for g in T["groups"]:
        gid = g["id"]
        st = group_standings(modal["group_results"], gid, modal["winners"], modal["runners_up"])
        third_code = st[2]["team"]
        third_note = "sneaks through as a best-third" if third_code in advancing_thirds \
            else "goes home despite third"
        order = " → ".join(
            f"**{name(s['team'])}** ({s['pts']}pts)" for s in st
        )
        lines.append(f"### Group {gid}")
        lines.append(f"Projected finish: {order}")
        lines.append(f"- 🥇 **{name(st[0]['team'])}** win it, **{name(st[1]['team'])}** "
                     f"follow them through. **{name(third_code)}** {third_note}; "
                     f"**{name(st[3]['team'])}** finish bottom.")
        for h in group_hooks(con, gid, pg_by_group[gid], st):
            lines.append(f"- {h}")
        lines.append("")
    return "\n".join(lines)


def knockout_section(per_game, probs):
    lines = ["## The knockouts — round by round\n"]
    rows_by_round = defaultdict(list)
    for r in per_game:
        if r["stage"] in ROUND_TITLES and r["stage"] != "FINAL":
            rows_by_round[r["stage"]].append(r)

    survival_key = {"R32": "p_r16", "R16": "p_qf", "QF": "p_semi", "SF": "p_final"}
    for rnd in ("R32", "R16", "QF", "SF"):
        rows = rows_by_round.get(rnd, [])
        if not rows:
            continue
        lines.append(f"### {ROUND_TITLES[rnd]}")
        coin_flips = [r for r in rows if r["decisiveness"] == "coin-flip"]
        comfy = [r for r in rows if r["decisiveness"] == "comfortable"]
        summary = f"The model expects {len(rows)} tie{'s' if len(rows) != 1 else ''} here"
        extra = []
        if comfy:
            extra.append(f"{len(comfy)} comfortable for the favourite")
        if coin_flips:
            extra.append(f"{len(coin_flips)} a genuine coin-flip" if len(coin_flips) == 1
                         else f"{len(coin_flips)} genuine coin-flips")
        if extra:
            summary += " — " + ", ".join(extra) + " that could swing on a single moment."
        lines.append(summary + ("" if summary.endswith(".") else "."))
        for r in rows:
            ph, pa = float(r["p_home"]), float(r["p_away"])
            fav, dog, fp = (r["home"], r["away"], ph) if ph >= pa else (r["away"], r["home"], pa)
            flag = " ⚠️ coin-flip" if r["decisiveness"] == "coin-flip" else ""
            lines.append(f"- **{name(fav)}** {pct(fp)} vs **{name(dog)}** — "
                         f"{r['character'].lower()}{flag}")
        lines.append("")
    return "\n".join(lines)


def final_section(con, per_game, modal, probs):
    fr = next(r for r in per_game if r["stage"] == "FINAL")
    t1, t2 = fr["home"], fr["away"]
    champ = modal["champion"]
    runner = t2 if champ == t1 else t1
    ph, pd, pa = float(fr["p_home"]), float(fr["p_draw"]), float(fr["p_away"])
    cp = ph if champ == t1 else pa
    rp = pa if champ == t1 else ph

    lines = ["## The final — and a champion\n"]
    lines.append(f"**{name(t1)} vs {name(t2)}** at the model's projected final.\n")
    lines.append(f"> {fr['character']}\n")
    lines.append(f"Head-to-head the engine splits it **{name(t1)} {pct(ph)} / "
                 f"draw {pct(pd)} / {name(t2)} {pct(pa)}** "
                 f"(expected goals {fr['exp_total_goals']}). ")
    if fr["decisiveness"] == "coin-flip":
        lines.append("This is no procession — it is the kind of final that lives on the "
                     "edge of extra time, where one set-piece or one penalty decides a "
                     "World Cup.\n")
    elif fr["decisiveness"] == "comfortable":
        lines.append("The model gives one side a clear edge — an upset would be a genuine "
                     "shock.\n")
    else:
        lines.append("A balanced, winnable-either-way final where small margins decide it.\n")

    for code in (t1, t2):
        stars = top_players(con, code, n=3)
        e = team_econ(con, code)
        if stars:
            star_str = ", ".join(
                f"{s.name}"
                + (f" ({s.xg90:.2f} xG/90)" if s.xg90 is not None else "")
                for s in stars)
            lines.append(f"- **{name(code)}** lean on: {star_str}.")
        if e:
            lines.append(f"  - FIFA #{e.fifa_rank}, {e.confederation}, "
                         f"{money(e.gdp_per_capita_usd)}/capita, {people(e.population)} people.")
    lines.append("")
    lines.append(f"### 🏆 Model's pick: **{name(champ)}**")
    lines.append(f"The simulation crowns **{name(champ)}** ({pct(cp)} to win the final over "
                 f"{name(runner)} at {pct(rp)}), and {pct(probs[champ]['p_champion'])} to lift "
                 f"the trophy across all {RUN_N:,} simulated tournaments.")
    return "\n".join(lines)


def headline_section(probs):
    ranked = sorted(probs.items(), key=lambda kv: (-kv[1]["p_champion"], kv[0]))
    champ, cp = ranked[0]
    lines = [f"# WC2026 — what the data actually predicts\n"]
    lines.append(f"Run off `data/wc2026.duckdb` — FIFA ranking, squad-aggregated player xG "
                 f"(attack/defense), and recent form — through {RUN_N:,} Monte Carlo "
                 f"tournaments (seed {RUN_SEED}). Economics and individual players are "
                 f"**narrative color only**; they never touch the prediction engine.\n")
    lines.append(f"## The model's favorite: **{name(champ)}** ({pct(cp['p_champion'])})\n")
    lines.append("| Rank | Team | Champion | Final | Semi | Quarter |")
    lines.append("|---|---|---|---|---|---|")
    for i, (code, p) in enumerate(ranked[:8], 1):
        lines.append(f"| {i} | {name(code)} | {pct(p['p_champion'])} | {pct(p['p_final'])} "
                     f"| {pct(p['p_semi'])} | {pct(p['p_qf'])} |")
    lines.append("")
    # Honest "no thumb on the scale" callout vs the popular hunch.
    hunch = {c: probs.get(c) for c in ("ESP", "NED", "ARG", "POR")}
    parts = [f"{name(c)} {pct(p['p_champion'])}" for c, p in hunch.items() if p]
    lines.append(f"**No thumb on the scale.** The popular pre-tournament chatter liked "
                 f"Spain and the Netherlands. The model doesn't fully agree — it has the "
                 f"four most-talked-about contenders at: {', '.join(parts)}. "
                 f"It rates **{name(champ)}** the most likely winner regardless of the "
                 f"narrative. The numbers below are the model's, not anyone's hopes.\n")
    return "\n".join(lines)


def caveats_section():
    return (
        "## How to read this (the honest footer)\n\n"
        f"- **Engine:** `ensemble = 0.35·Elo(FIFA) + 0.45·xG-Poisson + 0.20·Form`, the "
        f"config that matched Pinnacle's accuracy in the WC2022 backtest.\n"
        "- **Match character** comes from the WC2022 *model-agreement taxonomy*: when all "
        "three component models agree (\"golden-zone\") the call is reliable even at modest "
        "confidence; when they three-way split, it's genuine noise — a coin-flip.\n"
        "- **Economics & players are color only.** GDP and population never enter the "
        "engine, so the model can't be accused of downgrading teams that overperform their "
        "wealth (Argentina, Morocco, Senegal).\n"
        f"- **Reproducible:** seed {RUN_SEED}, {RUN_N:,} simulations. Same seed → same report.\n"
        "- Knockout matchups shown are the *modal* (most-likely) bracket; real draws will "
        "diverge, which is why per-team survival odds (the tables) matter more than any one "
        "projected tie.\n"
        "\n*Full per-match probabilities in `per_game.csv`; data lineage in `DATA_LINEAGE.md`.*\n"
    )


def main():
    probs, per_game, modal, T = load()
    con = connect()
    try:
        report = "\n\n".join(s.rstrip() for s in [
            headline_section(probs),
            group_section(con, T, per_game, modal),
            knockout_section(per_game, probs),
            final_section(con, per_game, modal, probs),
            caveats_section(),
        ]) + "\n"
    finally:
        con.close()

    (OUT / "REPORT.md").write_text(report)
    print(f"Saved → {OUT.relative_to(ROOT)}/REPORT.md ({len(report.splitlines())} lines)")


if __name__ == "__main__":
    main()
