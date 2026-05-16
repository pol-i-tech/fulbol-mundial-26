"""wc2026-predictor — Monte Carlo tournament simulator with luck factor.

Runs N WC2026 simulations using lambdas + sigmas computed by model.py. For
every simulated match, draws independent per-team luck perturbations:

    epsilon_team ~ Normal(0, sigma_team)   truncated to [-2*sigma, +2*sigma]
    lambda_eff   = clip(lambda_team + epsilon, LAMBDA_FLOOR, LAMBDA_MAX)
    goals        ~ Poisson(lambda_eff)

Knockout matches that draw in regulation simulate extra time (30 min ~ 1/3 of
90), then a penalty shootout coin-flip weighted by relative lambdas.

Outputs (in results/wc2026-predictor/<today>/):

  probabilities.{csv,json}
    Per-team stage-reach probabilities. Columns:
      team, team_code, p_top2_in_group, p_r32, p_r16, p_qf, p_semi,
      p_final, p_champion.

  predictions.csv (appended to)
    The closed-form group-stage rows from model.py PLUS one trio of
    match_1x2 rows per (team_a, team_b, stage) knockout pairing that
    appears in >= MIN_APPEARANCE_SHARE of iterations. p_draw is 0 for
    knockout rows (ET + penalties resolve every match). match_id format
    WC26-<STAGE>-<team_a>-<team_b>, team_a < team_b lexicographically.

  marquee_games.csv
    Up to MAX_MARQUEE group-stage fixtures where both teams have
    p_top2_in_group >= MARQUEE_MIN_P_TOP2, sorted by combined p_top2 desc.

Plan: docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md (Unit 4)
      docs/plans/2026-05-15-004-refactor-project-cleanup-plan.md (Unit 5 step 2)
      docs/plans/2026-05-16-001-feat-tournament-report-writer-agent-plan.md (Unit 1)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB_PATH = ROOT / "data" / "wc2026.duckdb"
TOURNAMENT_PATH = ROOT / "data" / "wc2026" / "tournament.json"
OUT_DIR_ROOT = ROOT / "results" / "wc2026-predictor"

# Knockout pairings emitted to predictions.csv only if they actually
# occurred in at least this fraction of MC iterations. With n=10000
# this is 100 occurrences; below that the per-pair winner share is too
# noisy to report.
MIN_APPEARANCE_SHARE = 0.01

# Marquee-game thresholds. A group-stage match is "marquee" when both
# teams cross MARQUEE_MIN_P_TOP2 — i.e., the model already considers
# both genuine top-2 contenders in their group. Capped at MAX_MARQUEE
# games sorted by combined p_top2 descending.
MARQUEE_MIN_P_TOP2 = 0.50
MAX_MARQUEE = 8


def _load_model_module():
    """Load methodology/wc2026-predictor/model.py as a Python module.

    The directory name contains a hyphen so we can't use a normal import.
    """
    spec = importlib.util.spec_from_file_location(
        "wc2026_predictor_model", HERE / "model.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wc2026_predictor_model"] = mod
    spec.loader.exec_module(mod)
    return mod


model = _load_model_module()


# ---------------------------------------------------------------------------
# Match sampling
# ---------------------------------------------------------------------------

def _draw_lambda_eff(lam: float, sigma: float, rng: np.random.Generator) -> float:
    """Draw a luck-perturbed effective lambda for one team for one match."""
    eps = rng.normal(0.0, sigma)
    eps = max(-2.0 * sigma, min(2.0 * sigma, eps))
    return float(np.clip(lam + eps, model.LAMBDA_FLOOR, model.LAMBDA_MAX))


def sim_match(
    home_code: str, away_code: str,
    by_code: pd.DataFrame,
    rng: np.random.Generator,
    knockout: bool = False,
) -> tuple[str | None, int, int]:
    """Simulate one match.

    Returns:
        (winner_code, home_goals, away_goals)
        winner_code is None in group-stage draws.
    """
    home = by_code.loc[home_code]
    away = by_code.loc[away_code]

    is_host = home_code in model.HOST_TEAM_CODES
    lam_h = home["lambda_team"] + (model.HOST_BOOST if is_host else 0.0)
    lam_a = away["lambda_team"]

    # v0.3: scale each team's lambda by the opponent's defensive quality
    # (xGA vs cohort avg, clipped).
    cohort_avg_xga = float(home["cohort_avg_xga"])
    home_attack_mult = model.defensive_factor(float(away["xga_team"]), cohort_avg_xga)
    away_attack_mult = model.defensive_factor(float(home["xga_team"]), cohort_avg_xga)
    lam_h = min(model.LAMBDA_MAX, lam_h * home_attack_mult)
    lam_a = min(model.LAMBDA_MAX, lam_a * away_attack_mult)

    lam_h_eff = _draw_lambda_eff(lam_h, home["sigma_team"], rng)
    lam_a_eff = _draw_lambda_eff(lam_a, away["sigma_team"], rng)

    g_h = int(rng.poisson(lam_h_eff))
    g_a = int(rng.poisson(lam_a_eff))

    if g_h > g_a:
        return home_code, g_h, g_a
    if g_a > g_h:
        return away_code, g_h, g_a
    if not knockout:
        return None, g_h, g_a

    # Knockout: extra time (30 min ≈ 1/3 of regulation Poisson)
    et_h = int(rng.poisson(lam_h_eff / 3.0))
    et_a = int(rng.poisson(lam_a_eff / 3.0))
    g_h += et_h
    g_a += et_a
    if g_h > g_a:
        return home_code, g_h, g_a
    if g_a > g_h:
        return away_code, g_h, g_a

    # Penalty shootout proxy: coin-flip weighted by relative effective lambdas
    p_home = lam_h_eff / (lam_h_eff + lam_a_eff)
    if rng.random() < p_home:
        return home_code, g_h, g_a
    return away_code, g_h, g_a


# ---------------------------------------------------------------------------
# Group stage
# ---------------------------------------------------------------------------

def sim_group(group: dict, by_code: pd.DataFrame, rng: np.random.Generator):
    """Simulate the 6 matches in one group. Returns standings sorted by rank."""
    pts = defaultdict(int)
    gd  = defaultdict(int)
    gs  = defaultdict(int)
    for match in group["matches"]:
        h, a = _resolve_team(match["home"], by_code), _resolve_team(match["away"], by_code)
        winner, g_h, g_a = sim_match(h, a, by_code, rng, knockout=False)
        gs[h] += g_h
        gs[a] += g_a
        gd[h] += g_h - g_a
        gd[a] += g_a - g_h
        if winner == h:
            pts[h] += 3
        elif winner == a:
            pts[a] += 3
        else:
            pts[h] += 1
            pts[a] += 1

    teams = [_resolve_team(t, by_code) for t in group["teams"]]
    teams.sort(key=lambda t: (-pts[t], -gd[t], -gs[t], rng.random()))
    return [
        {"team_code": t, "pts": pts[t], "gd": gd[t], "gs": gs[t]}
        for t in teams
    ]


def pick_third_places(all_thirds: list[dict], slot_rules: dict[str, list[str]]) -> dict[str, str]:
    """Assign the 8 best third-place teams to R32 slots respecting slot_to_groups."""
    ranked = sorted(all_thirds, key=lambda x: (-x["pts"], -x["gd"], -x["gs"]))
    top8 = ranked[:8]
    assignments: dict[str, str] = {}
    used: set[str] = set()
    for slot_id, valid_groups in slot_rules.items():
        for cand in top8:
            if cand["team_code"] in used:
                continue
            if cand["group_id"] in valid_groups:
                assignments[slot_id] = cand["team_code"]
                used.add(cand["team_code"])
                break
        if slot_id not in assignments:
            for cand in top8:
                if cand["team_code"] not in used:
                    assignments[slot_id] = cand["team_code"]
                    used.add(cand["team_code"])
                    break
    return assignments


# ---------------------------------------------------------------------------
# Knockout bracket
# ---------------------------------------------------------------------------

def _resolve_slot(
    slot: str,
    winners: dict[str, str],
    runners_up: dict[str, str],
    thirds: dict[str, str],
    match_winners: dict[str, str],
    match_losers: dict[str, str],
    group_id_for_third: str | None = None,
) -> str:
    if slot.startswith("1") and len(slot) == 2:
        return winners[slot[1]]
    if slot.startswith("2") and len(slot) == 2:
        return runners_up[slot[1]]
    if slot.startswith("3"):
        return thirds[group_id_for_third]
    if slot.startswith("W"):
        key = slot[1:]
        return match_winners["M" + key if key.isdigit() else key]
    if slot.startswith("L"):
        key = slot[1:]
        return match_losers["M" + key if key.isdigit() else key]
    raise ValueError(f"Cannot resolve slot {slot!r}")


def sim_bracket(
    tournament: dict,
    winners: dict[str, str],
    runners_up: dict[str, str],
    thirds: dict[str, str],
    by_code: pd.DataFrame,
    rng: np.random.Generator,
) -> tuple[dict[str, str], dict[str, str], list[dict]]:
    """Simulate every knockout match.

    Returns:
        match_winners: dict[match_id, team_code]
        match_losers:  dict[match_id, team_code]
        match_records: list of {"stage", "team_a", "team_b", "winner"} for
                       every knockout match in this iteration, in bracket
                       order. Used by run() to tally per-pair-per-stage counts.
    """
    match_winners: dict[str, str] = {}
    match_losers: dict[str, str] = {}
    match_records: list[dict] = []
    bracket = tournament["bracket"]

    def resolve(slot: str, third_slot_id: str | None = None) -> str:
        return _resolve_slot(slot, winners, runners_up, thirds, match_winners, match_losers, third_slot_id)

    # R32
    for m in bracket["r32"]:
        t1 = resolve(m["slot_a"], m["id"])
        t2 = resolve(m["slot_b"], m["id"])
        winner, _, _ = sim_match(t1, t2, by_code, rng, knockout=True)
        loser = t2 if winner == t1 else t1
        match_winners[m["id"]] = winner
        match_losers[m["id"]] = loser
        match_records.append({"stage": "r32", "team_a": t1, "team_b": t2, "winner": winner})

    # R16, QF, SF — slot_a / slot_b reference prior winners
    for round_key, stage_label in (("r16", "r16"), ("quarterfinals", "qf"), ("semifinals", "sf")):
        for m in bracket[round_key]:
            t1 = resolve(m["slot_a"])
            t2 = resolve(m["slot_b"])
            winner, _, _ = sim_match(t1, t2, by_code, rng, knockout=True)
            loser = t2 if winner == t1 else t1
            match_winners[m["id"]] = winner
            match_losers[m["id"]] = loser
            match_records.append({"stage": stage_label, "team_a": t1, "team_b": t2, "winner": winner})

    # Final
    f = bracket["final"][0]
    t1 = resolve(f["slot_a"])
    t2 = resolve(f["slot_b"])
    winner, _, _ = sim_match(t1, t2, by_code, rng, knockout=True)
    loser = t2 if winner == t1 else t1
    match_winners[f["id"]] = winner
    match_losers[f["id"]] = loser
    match_records.append({"stage": "final", "team_a": t1, "team_b": t2, "winner": winner})

    return match_winners, match_losers, match_records


# ---------------------------------------------------------------------------
# Team-name resolution
# ---------------------------------------------------------------------------

_RESOLVER_CACHE: dict[str, str] | None = None


def _build_resolver(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    aliases = {
        "Czechia": "Czech Republic",
        "USA": "United States",
        "Türkiye": "Turkey",
        "Cape Verde": "Cabo Verde",
        "South Korea": "Korea Republic",
        "Ivory Coast": "Côte d'Ivoire",
        "DR Congo": "Congo DR",
    }
    rows = con.sql("SELECT team_code, team_name FROM curated.dim_team").df()
    by_name = {r["team_name"]: r["team_code"] for _, r in rows.iterrows()}
    by_name.update({name: by_name[canon] for name, canon in aliases.items() if canon in by_name})
    return by_name


def _resolve_team(name: str, by_code: pd.DataFrame) -> str:
    global _RESOLVER_CACHE
    if _RESOLVER_CACHE is None:
        raise RuntimeError("Team resolver not initialised; call run() not _resolve_team directly")
    code = _RESOLVER_CACHE.get(name)
    if code is None or code not in by_code.index:
        raise RuntimeError(f"Tournament team {name!r} does not resolve to a dim_team row")
    return code


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(n: int, seed: int, db_path: Path, out_dir: Path) -> Path:
    global _RESOLVER_CACHE
    rng = np.random.default_rng(seed)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        features = model.load_features(con)
        lambdas = model.compute_lambdas(features)
        _RESOLVER_CACHE = _build_resolver(con)
    finally:
        con.close()

    tournament = json.loads(TOURNAMENT_PATH.read_text())
    by_code = lambdas.set_index("team_code")

    # Pre-flight: every team in the tournament JSON must resolve and have lambdas
    for g in tournament["groups"]:
        for name in g["teams"]:
            _resolve_team(name, by_code)

    # Tallies: how many runs each team reached each stage / finished top-2 in group.
    counts = defaultdict(lambda: {"top2_in_group": 0, "r32": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0, "champion": 0})
    bracket = tournament["bracket"]

    # Per-pair-per-stage knockout tallies. Key is (team_a, team_b, stage)
    # with team_a < team_b lexicographically to dedupe (Germany, France)
    # vs. (France, Germany).
    pair_appearances: dict[tuple[str, str, str], int] = defaultdict(int)
    pair_wins: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for run_i in range(n):
        group_results: dict[str, list[dict]] = {}
        winners: dict[str, str] = {}
        runners_up: dict[str, str] = {}
        thirds_pool: list[dict] = []

        for g in tournament["groups"]:
            standings = sim_group(g, by_code, rng)
            group_results[g["id"]] = standings
            winners[g["id"]] = standings[0]["team_code"]
            runners_up[g["id"]] = standings[1]["team_code"]
            thirds_pool.append({**standings[2], "group_id": g["id"]})
            # Top-2 in group: standings[0] and standings[1] always advance from a
            # 4-team group simulation (3rd-place qualification is the dim layer above).
            counts[standings[0]["team_code"]]["top2_in_group"] += 1
            counts[standings[1]["team_code"]]["top2_in_group"] += 1

        thirds_assignments = pick_third_places(thirds_pool, tournament["third_place_rules"]["slot_to_groups"])

        # Every team that started the tournament reaches R32
        for g in tournament["groups"]:
            for t in g["teams"]:
                code = _resolve_team(t, by_code)
                counts[code]["r32"] += 1

        match_winners, _, match_records = sim_bracket(
            tournament, winners, runners_up, thirds_assignments, by_code, rng
        )

        # Per-pair-per-stage tallies for knockout match-level probabilities
        for rec in match_records:
            a, b = sorted([rec["team_a"], rec["team_b"]])
            key = (a, b, rec["stage"])
            pair_appearances[key] += 1
            pair_wins[key][rec["winner"]] += 1

        # Walk the bracket and tally stage reaches
        r32_ids = [m["id"] for m in bracket["r32"]]
        for mid in r32_ids:
            counts[match_winners[mid]]["r16"] += 1
        r16_ids = [m["id"] for m in bracket["r16"]]
        for mid in r16_ids:
            counts[match_winners[mid]]["qf"] += 1
        qf_ids = [m["id"] for m in bracket["quarterfinals"]]
        for mid in qf_ids:
            counts[match_winners[mid]]["sf"] += 1
        sf_ids = [m["id"] for m in bracket["semifinals"]]
        for mid in sf_ids:
            counts[match_winners[mid]]["final"] += 1
        final_id = bracket["final"][0]["id"]
        counts[match_winners[final_id]]["champion"] += 1

    out_dir.mkdir(parents=True, exist_ok=True)

    # ── probabilities.{csv,json}: per-team stage-reach + top-2-in-group ────
    rows = []
    for code, c in counts.items():
        rows.append({
            "team":            by_code.loc[code, "team_name"],
            "team_code":       code,
            "p_top2_in_group": round(c["top2_in_group"] / n, 4),
            "p_r32":           round(c["r32"]      / n, 4),
            "p_r16":           round(c["r16"]      / n, 4),
            "p_qf":            round(c["qf"]       / n, 4),
            "p_semi":          round(c["sf"]       / n, 4),
            "p_final":         round(c["final"]    / n, 4),
            "p_champion":      round(c["champion"] / n, 4),
        })
    out = pd.DataFrame(rows).sort_values("p_champion", ascending=False)

    csv_path = out_dir / "probabilities.csv"
    json_path = out_dir / "probabilities.json"
    out.to_csv(csv_path, index=False)
    out.to_json(json_path, orient="records", indent=2)

    # ── predictions.csv: append per-match knockout rows ───────────────────
    _append_knockout_predictions(out_dir, pair_appearances, pair_wins, n)

    # ── marquee_games.csv: rule-based shortlist of marquee group fixtures ─
    _write_marquee_games(out_dir, tournament, by_code, counts, n)

    return csv_path


def _append_knockout_predictions(
    out_dir: Path,
    pair_appearances: dict[tuple[str, str, str], int],
    pair_wins: dict[tuple[str, str, str], dict[str, int]],
    n: int,
) -> None:
    """Append per-pair-per-stage match_1x2 rows to predictions.csv.

    Group-stage rows produced by model.py are preserved. For each knockout
    pair (team_a < team_b lexicographically) appearing in >= MIN_APPEARANCE_SHARE
    of iterations, emit three rows: home (team_a wins), draw (always 0 — ET
    + penalties resolve every match), away (team_b wins).
    """
    predictions_path = out_dir / "predictions.csv"
    if not predictions_path.exists():
        # model.py hasn't been run for this snapshot date — nothing to append to
        return

    existing = pd.read_csv(predictions_path)

    # If a previous simulate.py run already appended knockout rows for this
    # snapshot, drop them before re-appending. Knockout match_ids look like
    # WC26-{R32,R16,QF,SF,FINAL}-XXX-YYY (no kickoff date suffix).
    ko_pattern = r"^WC26-(R32|R16|QF|SF|FINAL)-"
    existing = existing[~existing["match_id"].astype(str).str.match(ko_pattern, na=False)].copy()

    today = date.today().isoformat()
    ko_rows: list[dict] = []
    for (a, b, stage), appearances in pair_appearances.items():
        share = appearances / n
        if share < MIN_APPEARANCE_SHARE:
            continue
        wins_a = pair_wins[(a, b, stage)].get(a, 0)
        wins_b = pair_wins[(a, b, stage)].get(b, 0)
        p_a = wins_a / appearances
        p_b = wins_b / appearances
        match_id = f"WC26-{stage.upper()}-{a}-{b}"
        notes = f"knockout stage={stage} appearance_share={share:.3f} n_pairings={appearances}"
        for outcome, p in [("home", p_a), ("draw", 0.0), ("away", p_b)]:
            ko_rows.append({
                "as_of_date":    today,
                "match_id":      match_id,
                "market_type":   "match_1x2",
                "outcome":       outcome,
                "p_model":       round(p, 4),
                # Conditional on both teams reaching this stage — appearance_share
                # captures how often the pair actually met.
                "confidence":    "low" if share < 0.05 else "medium",
                "model_version": model.MODEL_VERSION,
                "notes":         notes,
            })

    if not ko_rows:
        return

    augmented = pd.concat([existing, pd.DataFrame(ko_rows)], ignore_index=True)
    augmented.to_csv(predictions_path, index=False)


def _write_marquee_games(
    out_dir: Path,
    tournament: dict,
    by_code: pd.DataFrame,
    counts: dict,
    n: int,
) -> None:
    """Emit results/wc2026-predictor/<today>/marquee_games.csv.

    A group-stage fixture qualifies if both teams have p_top2_in_group >=
    MARQUEE_MIN_P_TOP2. Sorted by combined p_top2 desc, capped at MAX_MARQUEE.
    Empty header-only file if no fixture clears the bar.
    """
    predictions_path = out_dir / "predictions.csv"
    columns = [
        "match_id", "home_code", "away_code", "home_team", "away_team",
        "group_letter", "kickoff_date", "p_home", "p_draw", "p_away",
        "lam_home", "lam_away", "p_top2_home", "p_top2_away",
    ]
    out_path = out_dir / "marquee_games.csv"

    if not predictions_path.exists():
        pd.DataFrame(columns=columns).to_csv(out_path, index=False)
        return

    top2_lookup = {code: c["top2_in_group"] / n for code, c in counts.items()}

    preds = pd.read_csv(predictions_path)
    group_preds = preds[~preds["match_id"].astype(str).str.match(r"^WC26-(R32|R16|QF|SF|FINAL)-", na=False)]
    group_wide = (
        group_preds.pivot_table(index="match_id", columns="outcome", values="p_model", aggfunc="first")
        .reset_index()
    )

    candidates: list[dict] = []
    for g in tournament["groups"]:
        for match in g["matches"]:
            h_code = _resolve_team(match["home"], by_code)
            a_code = _resolve_team(match["away"], by_code)
            p_top2_h = top2_lookup.get(h_code, 0.0)
            p_top2_a = top2_lookup.get(a_code, 0.0)
            if min(p_top2_h, p_top2_a) < MARQUEE_MIN_P_TOP2:
                continue
            match_id = f"WC26-{h_code}-{a_code}-{match['date']}"
            row = group_wide[group_wide["match_id"] == match_id]
            if row.empty:
                continue
            r = row.iloc[0]
            candidates.append({
                "match_id":     match_id,
                "home_code":    h_code,
                "away_code":    a_code,
                "home_team":    by_code.loc[h_code, "team_name"],
                "away_team":    by_code.loc[a_code, "team_name"],
                "group_letter": g["id"],
                "kickoff_date": match["date"],
                "p_home":       float(r.get("home", 0.0)),
                "p_draw":       float(r.get("draw", 0.0)),
                "p_away":       float(r.get("away", 0.0)),
                "lam_home":     float(by_code.loc[h_code, "lambda_team"]),
                "lam_away":     float(by_code.loc[a_code, "lambda_team"]),
                "p_top2_home":  round(p_top2_h, 4),
                "p_top2_away":  round(p_top2_a, 4),
            })

    candidates.sort(key=lambda x: -(x["p_top2_home"] + x["p_top2_away"]))
    top = candidates[:MAX_MARQUEE]

    pd.DataFrame(top, columns=columns).to_csv(out_path, index=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(argv)

    db = Path(args.db_path)
    if not db.exists():
        raise FileNotFoundError(f"DuckDB not found at {db}")

    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR_ROOT / date.today().isoformat()
    csv_path = run(args.n, args.seed, db, out_dir)
    print(f"Wrote tournament probabilities ({args.n} sims, seed={args.seed}) -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
