"""Export the wc2026-predictor snapshot to docs/data.json for the public web report.

Reads (in order):
  1. results/wc2026-predictor/<latest-date>/probabilities.csv  — per-team stage-reach
     probabilities including the new p_top2_in_group column.
  2. data/wc2026/tournament.json                                — bracket / group config.
  3. curated.dim_team in data/wc2026.duckdb                    — display names + confederation.

Writes docs/data.json with the shape docs/index.html consumes:
  meta, teams[], bracket{}, model_agreement[]

The per-team `ratings` dict and `market` dict that the multi-model era emitted are
gone — docs/index.html does not consume those keys (verified before this refactor).
`model_agreement` is emitted as an empty list because the project has consolidated
to a single canonical model; there is nothing to compare. The renderer in
docs/index.html handles an empty array gracefully.

Usage:
    python3 tools/export_web_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).parent.parent
RESULTS_ROOT = REPO / "results" / "wc2026-predictor"
DB_PATH = REPO / "data" / "wc2026.duckdb"
TOURNAMENT_PATH = REPO / "data" / "wc2026" / "tournament.json"
OUT_PATH = REPO / "docs" / "data.json"
DATE_RE = "????-??-??"


def find_latest_snapshot() -> Path:
    """Return the most recent results/wc2026-predictor/YYYY-MM-DD/ folder.

    Exits with a clear pointer if no snapshot exists yet.
    """
    candidates = sorted(p for p in RESULTS_ROOT.glob(DATE_RE) if p.is_dir())
    if not candidates:
        print(
            "No wc2026-predictor snapshot found under "
            f"{RESULTS_ROOT.relative_to(REPO)}.\n"
            "Run the model first:\n"
            "  python3 methodology/wc2026-predictor/model.py\n"
            "  python3 methodology/wc2026-predictor/simulate.py",
            file=sys.stderr,
        )
        sys.exit(1)
    return candidates[-1]


def load_probabilities(snapshot_dir: Path) -> dict[str, dict]:
    """Load probabilities.csv, keyed by display team name.

    Returns the same shape the bracket/team derivation code expects:
      {team_name: {champion, final, sf, qf, r16, r32, top2}}
    """
    path = snapshot_dir / "probabilities.csv"
    if not path.exists():
        print(
            f"Missing {path.relative_to(REPO)}.\n"
            "Run: python3 methodology/wc2026-predictor/simulate.py",
            file=sys.stderr,
        )
        sys.exit(1)
    df = pd.read_csv(path)
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        out[row["team"]] = {
            "champion": float(row["p_champion"]),
            "final":    float(row["p_final"]),
            "sf":       float(row["p_semi"]),
            "qf":       float(row["p_qf"]),
            "r16":      float(row["p_r16"]),
            "r32":      float(row["p_r32"]),
            "top2":     float(row["p_top2_in_group"]),
        }
    if len(out) != 48:
        print(f"Expected 48 teams in {path.relative_to(REPO)}, got {len(out)}", file=sys.stderr)
        sys.exit(1)
    return out


def load_team_metadata() -> dict[str, dict]:
    """Read curated.dim_team. Returns {team_name: {team_code, confederation}}."""
    if not DB_PATH.exists():
        print(
            f"Missing {DB_PATH.relative_to(REPO)}.\n"
            "Run: python3 tools/build_duckdb.py",
            file=sys.stderr,
        )
        sys.exit(1)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.sql(
            "SELECT team_name, team_code, confederation "
            "FROM curated.dim_team WHERE is_wc2026_qualifier"
        ).df()
    finally:
        con.close()
    return {r["team_name"]: {"team_code": r["team_code"], "confederation": r["confederation"]}
            for _, r in rows.iterrows()}


def confidence_from_top2(p_top2: float) -> str:
    """Map p_top2_in_group to a HIGH/MEDIUM/LOW confidence label.

    Replaces the multi-model M2_Season-based confidence calc. The new signal is
    a direct readout of how strongly the model believes a team advances from
    its group.
    """
    if p_top2 >= 0.70:
        return "HIGH"
    if p_top2 >= 0.40:
        return "MEDIUM"
    return "LOW"


def _head_to_head_pct(t1_prob: float, t2_prob: float) -> tuple[float, float]:
    """Convert raw stage-reach probabilities to a head-to-head win split."""
    total = t1_prob + t2_prob
    if total <= 0:
        return 50.0, 50.0
    p1 = round(t1_prob / total * 100, 1)
    return p1, round(100 - p1, 1)


def derive_bracket(probs: dict[str, dict], tournament: dict) -> dict:
    """Derive a single predicted bracket path from per-team stage-reach probs."""
    groups_cfg = tournament["groups"]
    bracket_cfg = tournament["bracket"]
    third_place_rules = tournament["third_place_rules"]["slot_to_groups"]

    group_results: dict[str, dict] = {}
    thirds_pool: list[dict] = []

    for g in groups_cfg:
        gid = g["id"]
        ranked = sorted(
            g["teams"],
            key=lambda t: probs.get(t, {}).get("champion", 0.0),
            reverse=True,
        )
        group_results[gid] = {
            "winner":    ranked[0],
            "runner_up": ranked[1],
            "teams":     g["teams"],
        }
        thirds_pool.append({
            "team":  ranked[2],
            "group": gid,
            "pct":   probs.get(ranked[2], {}).get("champion", 0.0),
        })

    thirds_pool.sort(key=lambda x: x["pct"], reverse=True)
    best_8 = thirds_pool[:8]
    best_thirds_by_group = {t["group"]: t["team"] for t in best_8}

    winners = {gid: r["winner"] for gid, r in group_results.items()}
    runners_up = {gid: r["runner_up"] for gid, r in group_results.items()}

    assigned_thirds: dict[str, str] = {}

    def _pick_third(match_id: str, valid_groups: list[str], remaining: dict[str, str]) -> str:
        for g in sorted(
            valid_groups,
            key=lambda x: -probs.get(remaining.get(x, ""), {}).get("champion", 0.0),
        ):
            if g in remaining:
                team = remaining.pop(g)
                assigned_thirds[match_id] = team
                return team
        return "TBD"

    remaining_thirds = dict(best_thirds_by_group)

    def resolve_slot(slot_str: str, match_id: str) -> str:
        if slot_str.startswith("1"):
            return winners.get(slot_str[1:], "TBD")
        if slot_str.startswith("2"):
            return runners_up.get(slot_str[1:], "TBD")
        if slot_str.startswith("3"):
            valid = third_place_rules.get(match_id, [])
            return _pick_third(match_id, valid, remaining_thirds)
        return "TBD"

    match_winners: dict[str, str] = {}

    def _slot_to_key(slot_str: str) -> str:
        suffix = slot_str[1:]
        return "M" + suffix if suffix.isdigit() else suffix

    def build_round(slots: list[dict], prob_key: str, source: str) -> list[dict]:
        matches = []
        for m in slots:
            if source == "slots":
                t1 = resolve_slot(m["slot_a"], m["id"])
                t2 = resolve_slot(m["slot_b"], m["id"])
            else:
                t1 = match_winners.get(_slot_to_key(m["slot_a"]), "TBD")
                t2 = match_winners.get(_slot_to_key(m["slot_b"]), "TBD")
            p1_raw = probs.get(t1, {}).get(prob_key, 0.0)
            p2_raw = probs.get(t2, {}).get(prob_key, 0.0)
            p1, p2 = _head_to_head_pct(p1_raw, p2_raw)
            winner = t1 if p1 >= p2 else t2
            match_winners[m["id"]] = winner
            matches.append({
                "match_id": m["id"],
                "team1":    t1,
                "team2":    t2,
                "p1":       p1,
                "p2":       p2,
                "winner":   winner,
            })
        return matches

    r32 = build_round(bracket_cfg["r32"], "r16", "slots")
    r16 = build_round(bracket_cfg["r16"], "qf", "winners")
    qf = build_round(bracket_cfg["quarterfinals"], "sf", "winners")
    sf = build_round(bracket_cfg["semifinals"], "final", "winners")
    final = build_round(bracket_cfg["final"], "champion", "winners")

    return {
        "groups": {
            gid: {
                "winner":    res["winner"],
                "runner_up": res["runner_up"],
                "teams":     res["teams"],
            }
            for gid, res in group_results.items()
        },
        "r32":      r32,
        "r16":      r16,
        "qf":       qf,
        "sf":       sf,
        "final":    final[0] if final else {},
        "champion": final[0]["winner"] if final else None,
    }


def main() -> int:
    snapshot_dir = find_latest_snapshot()
    snapshot_date = snapshot_dir.name

    probs = load_probabilities(snapshot_dir)
    team_meta = load_team_metadata()

    with TOURNAMENT_PATH.open() as f:
        tournament = json.load(f)

    teams: list[dict] = []
    for rank, (team, p) in enumerate(
        sorted(probs.items(), key=lambda x: x[1]["champion"], reverse=True), 1
    ):
        if team not in team_meta:
            print(f"Team {team!r} from probabilities.csv has no curated.dim_team row.", file=sys.stderr)
            sys.exit(1)
        teams.append({
            "rank":           rank,
            "name":           team,
            "champion_pct":   round(p["champion"] * 100, 1),
            "final_pct":      round(p["final"]    * 100, 1),
            "semi_pct":       round(p["sf"]       * 100, 1),
            "group_exit_pct": round((1 - p["top2"]) * 100, 1),
            "top2_pct":       round(p["top2"]     * 100, 1),
            "confidence":     confidence_from_top2(p["top2"]),
        })

    bracket = derive_bracket(probs, tournament)

    output = {
        "meta": {
            "generated":  snapshot_date,
            "model":      "wc2026-predictor",
            "model_card": "results/wc2026-predictor/MODEL.md",
            "simulations": 10000,
            "note": (
                "Probabilities are model estimates from a 10k-iter Monte Carlo bracket "
                "simulation against curated team features. The bracket below is the "
                "single most-likely path; the real tournament will look different."
            ),
        },
        "teams":           teams,
        "bracket":         bracket,
        # The model_agreement panel was meaningful in the multi-model era;
        # the project has consolidated to one canonical model. Emitted empty
        # for shape stability; docs/index.html renders the panel as empty.
        "model_agreement": [],
    }

    OUT_PATH.parent.mkdir(exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUT_PATH.relative_to(REPO)} (snapshot {snapshot_date})")
    print(f"  Teams: {len(teams)}")
    print(f"  Champion (most likely path): {bracket['champion']}")
    if bracket["final"]:
        print(f"  Final (most likely path): {bracket['final'].get('team1')} vs {bracket['final'].get('team2')}")
    low = sum(1 for t in teams if t["confidence"] == "LOW")
    high = sum(1 for t in teams if t["confidence"] == "HIGH")
    print(f"  Confidence: {high} HIGH / {48 - low - high} MEDIUM / {low} LOW")
    return 0


if __name__ == "__main__":
    sys.exit(main())
