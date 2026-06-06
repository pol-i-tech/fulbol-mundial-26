#!/usr/bin/env python3
"""
WC2026 tournament simulator wired to the curated DuckDB ratings.

- Reads team ratings from `curated.dim_team_current` (FIFA points) and
  `curated.fact_team_rating` (attack, defense, recent_form) at data/wc2026.duckdb.
- Reads the bracket from data/wc2026/tournament.json.
- Predicts each match via the ensemble-e3 weighting:
    0.35 * Elo (FIFA points)  +  0.45 * Poisson (attack/defense)  +  0.20 * Form
- Runs Monte Carlo to estimate per-stage probabilities AND a single
  "modal path" run (per-match most-likely outcome) for a deterministic bracket.

Usage:
  python3 tools/simulate_wc2026_duckdb.py [--n 20000] [--seed 42]
"""
import argparse, json, math, csv, sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from lib.match_character import classify_match  # noqa: E402

DB   = ROOT / "data" / "wc2026.duckdb"
TJ   = ROOT / "data" / "wc2026" / "tournament.json"
OUT  = ROOT / "results" / "wc2026-sim-duckdb"
OUT.mkdir(parents=True, exist_ok=True)

W_ELO, W_POI, W_FORM = 0.35, 0.45, 0.20

# tournament.json uses display names; DuckDB uses canonical names. Bridge them.
NAME_TO_CODE = {
    "Mexico": "MEX", "South Africa": "RSA", "Czechia": "CZE", "South Korea": "KOR",
    "Canada": "CAN", "Bosnia and Herzegovina": "BIH", "Qatar": "QAT", "Switzerland": "SUI",
    "Brazil": "BRA", "Morocco": "MAR", "Haiti": "HAI", "Scotland": "SCO",
    "USA": "USA", "Paraguay": "PAR", "Australia": "AUS", "Türkiye": "TUR",
    "Germany": "GER", "Curaçao": "CUW", "Ivory Coast": "CIV", "Ecuador": "ECU",
    "Netherlands": "NED", "Japan": "JPN", "Sweden": "SWE", "Tunisia": "TUN",
    "Belgium": "BEL", "Egypt": "EGY", "Iran": "IRI", "New Zealand": "NZL",
    "Spain": "ESP", "Cape Verde": "CPV", "Saudi Arabia": "KSA", "Uruguay": "URU",
    "France": "FRA", "Senegal": "SEN", "Iraq": "IRQ", "Norway": "NOR",
    "Argentina": "ARG", "Algeria": "ALG", "Austria": "AUT", "Jordan": "JOR",
    "Portugal": "POR", "DR Congo": "COD", "Uzbekistan": "UZB", "Colombia": "COL",
    "England": "ENG", "Croatia": "CRO", "Ghana": "GHA", "Panama": "PAN",
}


def load_ratings():
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute("""
        SELECT
          t.team_code,
          t.fifa_points,
          MAX(CASE WHEN r.rating_type='attack'      THEN r.rating_value END) AS attack,
          MAX(CASE WHEN r.rating_type='defense'     THEN r.rating_value END) AS defense,
          MAX(CASE WHEN r.rating_type='recent_form' THEN r.rating_value END) AS form
        FROM curated.dim_team_current t
        LEFT JOIN curated.fact_team_rating r ON t.team_code = r.team_code
        WHERE t.is_wc2026_qualifier
        GROUP BY 1, 2
    """).df()
    con.close()

    # Sensible fallbacks: median of qualifier pool
    attack_fb  = float(df["attack"].median(skipna=True))   # ~0.32 xG/90
    defense_fb = float(df["defense"].median(skipna=True))  # ~1.35 xGA/90
    form_fb    = float(df["form"].median(skipna=True))     # ~0.40

    out = {}
    for _, r in df.iterrows():
        out[r.team_code] = {
            "fifa":    float(r.fifa_points),
            "attack":  attack_fb  if (r.attack  is None or math.isnan(r.attack))  else float(r.attack),
            "defense": defense_fb if (r.defense is None or math.isnan(r.defense)) else float(r.defense),
            "form":    form_fb    if (r.form    is None or math.isnan(r.form))    else float(r.form),
        }
    return out


# ── three component models ─────────────────────────────────────────────────────
def elo_probs(home_pts, away_pts):
    """FIFA points → 1X2. (Tournament matches are neutral, so no home adv.)"""
    p_home = 1.0 / (1.0 + 10 ** ((away_pts - home_pts) / 400.0))
    # Carve out a draw probability from the two win sides
    # Empirical WC: P(draw) ≈ 0.28 - 0.20*|p_home - 0.5|*2
    margin = abs(p_home - 0.5) * 2
    p_draw = max(0.10, 0.30 - 0.18 * margin)
    p_home_only = (1 - p_draw) * p_home
    p_away_only = (1 - p_draw) * (1 - p_home)
    return p_home_only, p_draw, p_away_only


def poisson_lambdas(home, away):
    """Attack (xG/90 proxy) × opponent defense (xGA/90)."""
    league_avg_goals = 1.30   # WC group-stage proxy
    lam_h = home["attack"] / (away["defense"] / league_avg_goals + 0.1) * 2.5
    lam_a = away["attack"] / (home["defense"] / league_avg_goals + 0.1) * 2.5
    # Clamp to reasonable WC range
    lam_h = max(0.35, min(2.80, lam_h))
    lam_a = max(0.35, min(2.80, lam_a))
    return lam_h, lam_a


def poisson_probs(lam_h, lam_a, max_g=8):
    """Independent Poisson → 1X2 probabilities."""
    ph = pd = pa = 0.0
    for i in range(max_g):
        for j in range(max_g):
            p = math.exp(-lam_h) * lam_h**i / math.factorial(i) * \
                math.exp(-lam_a) * lam_a**j / math.factorial(j)
            if   i > j: ph += p
            elif i < j: pa += p
            else:       pd += p
    s = ph + pd + pa
    return ph/s, pd/s, pa/s


def form_probs(home_form, away_form):
    """Map form deltas to 1X2 (small effect)."""
    delta = home_form - away_form
    p_home = 1.0 / (1.0 + math.exp(-2.5 * delta))
    p_draw = 0.30
    return (1 - p_draw) * p_home, p_draw, (1 - p_draw) * (1 - p_home)


def ensemble_probs(home, away):
    eh, ed, ea = elo_probs(home["fifa"], away["fifa"])
    lam_h, lam_a = poisson_lambdas(home, away)
    ph, pd_, pa = poisson_probs(lam_h, lam_a)
    fh, fd, fa = form_probs(home["form"], away["form"])
    H = W_ELO*eh + W_POI*ph + W_FORM*fh
    D = W_ELO*ed + W_POI*pd_ + W_FORM*fd
    A = W_ELO*ea + W_POI*pa + W_FORM*fa
    s = H + D + A
    return H/s, D/s, A/s, lam_h, lam_a


def _argmax_1x2(h, d, a):
    """1X2 outcome label of the most likely of three probabilities."""
    if h >= d and h >= a:
        return "H"
    if a >= d and a >= h:
        return "A"
    return "D"


def component_picks(home, away):
    """Each component model's 1X2 pick (Elo, Poisson, Form) — for the
    match-character model-agreement band (WC2022 disagreement taxonomy)."""
    eh, ed, ea = elo_probs(home["fifa"], away["fifa"])
    lam_h, lam_a = poisson_lambdas(home, away)
    ph, pd_, pa = poisson_probs(lam_h, lam_a)
    fh, fd, fa = form_probs(home["form"], away["form"])
    return (_argmax_1x2(eh, ed, ea),
            _argmax_1x2(ph, pd_, pa),
            _argmax_1x2(fh, fd, fa))


# ── simulation primitives ──────────────────────────────────────────────────────
def sim_match_group(home_code, away_code, ratings, rng):
    """Group-stage: returns (gh, ga) using independent Poisson on ensemble λs."""
    _, _, _, lam_h, lam_a = ensemble_probs(ratings[home_code], ratings[away_code])
    return rng.poisson(lam_h), rng.poisson(lam_a)


def sim_match_ko(t1_code, t2_code, ratings, rng):
    """Knockout: returns winning code. Uses ensemble 1X2; resolves draws by
    weighted coin (proxy for ET + penalties)."""
    pH, pD, pA, _, _ = ensemble_probs(ratings[t1_code], ratings[t2_code])
    r = rng.random()
    if r < pH: return t1_code
    if r < pH + pA: return t2_code
    # Draw → coin biased by underlying win probs
    return t1_code if rng.random() < pH / (pH + pA) else t2_code


def sim_group(group, ratings, rng):
    teams = [NAME_TO_CODE[t] for t in group["teams"]]
    pts = defaultdict(int); gd = defaultdict(int); gs = defaultdict(int)
    for m in group["matches"]:
        h, a = NAME_TO_CODE[m["home"]], NAME_TO_CODE[m["away"]]
        gh, ga = sim_match_group(h, a, ratings, rng)
        gs[h] += gh; gs[a] += ga
        gd[h] += gh - ga; gd[a] += ga - gh
        if gh > ga:   pts[h] += 3
        elif gh < ga: pts[a] += 3
        else:         pts[h] += 1; pts[a] += 1
    standings = sorted(teams, key=lambda t: (-pts[t], -gd[t], -gs[t], rng.random()))
    return [{"team": t, "pts": pts[t], "gd": gd[t], "gs": gs[t]} for t in standings]


def assign_thirds(thirds, rules):
    ranked = sorted(thirds, key=lambda x: (-x["pts"], -x["gd"], -x["gs"]))[:8]
    out, used = {}, set()
    for slot_id, valid in rules["slot_to_groups"].items():
        chosen = None
        for c in ranked:
            if c["team"] in used: continue
            if c["group_id"] in valid:
                chosen = c["team"]; break
        if chosen is None:
            for c in ranked:
                if c["team"] not in used:
                    chosen = c["team"]; break
        out[slot_id] = chosen; used.add(chosen)
    return out


def sim_bracket(winners, runners_up, thirds, T, ratings, rng):
    brk = T["bracket"]
    wins = {}
    for m in brk["r32"]:
        t1 = resolve_slot(m["slot_a"], winners, runners_up, thirds, m["id"])
        t2 = resolve_slot(m["slot_b"], winners, runners_up, thirds, m["id"])
        wins[m["id"]] = sim_match_ko(t1, t2, ratings, rng)
    def lkp(slot):
        return wins["M" + slot[1:]]
    for rk in ("r16", "quarterfinals", "semifinals"):
        for m in brk[rk]:
            wins[m["id"]] = sim_match_ko(lkp(m["slot_a"]), lkp(m["slot_b"]), ratings, rng)
    f = brk["final"][0]
    sf_w = {"SF1": wins["SF1"], "SF2": wins["SF2"]}
    final_t1 = sf_w[f["slot_a"][1:]]  # WSF1 → SF1
    final_t2 = sf_w[f["slot_b"][1:]]
    wins["FINAL"] = sim_match_ko(final_t1, final_t2, ratings, rng)
    return wins


def resolve_slot(slot, winners, runners_up, thirds, mid):
    if slot[0] == "1": return winners[slot[1]]
    if slot[0] == "2": return runners_up[slot[1]]
    if slot[0] == "3": return thirds.get(mid)
    return None


# ── runner ─────────────────────────────────────────────────────────────────────
def monte_carlo(T, ratings, n, seed):
    rng = np.random.default_rng(seed)
    stages = ["r32", "r16", "qf", "sf", "final", "champion"]
    all_teams = set()
    for g in T["groups"]:
        for t in g["teams"]: all_teams.add(NAME_TO_CODE[t])
    counts = {t: {s: 0 for s in stages} for t in all_teams}
    rules = T["third_place_rules"]

    for _ in range(n):
        winners, runners_up, thirds_pool = {}, {}, []
        for g in T["groups"]:
            st = sim_group(g, ratings, rng)
            winners[g["id"]]    = st[0]["team"]
            runners_up[g["id"]] = st[1]["team"]
            thirds_pool.append({**st[2], "group_id": g["id"]})
        thirds = assign_thirds(thirds_pool, rules)
        r32 = set(winners.values()) | set(runners_up.values()) | set(thirds.values())
        for t in r32: counts[t]["r32"] += 1

        wins = sim_bracket(winners, runners_up, thirds, T, ratings, rng)

        for m in T["bracket"]["r16"]:
            counts[wins["M" + m["slot_a"][1:]]]["r16"] += 1
            counts[wins["M" + m["slot_b"][1:]]]["r16"] += 1
        for m in T["bracket"]["quarterfinals"]:
            counts[wins["M" + m["slot_a"][1:]]]["qf"] += 1
            counts[wins["M" + m["slot_b"][1:]]]["qf"] += 1
        for m in T["bracket"]["semifinals"]:
            counts[wins["M" + m["slot_a"][1:]]]["sf"] += 1
            counts[wins["M" + m["slot_b"][1:]]]["sf"] += 1
        counts[wins["SF1"]]["final"] += 1
        counts[wins["SF2"]]["final"] += 1
        counts[wins["FINAL"]]["champion"] += 1

    return {t: {s: counts[t][s] / n for s in stages} for t in all_teams}


def modal_path(T, ratings):
    """Single deterministic 'most-likely outcome' bracket. For each game,
    pick the highest-probability 1X2 outcome (group: H/D/A); for knockouts,
    pick the higher of (pH, pA)."""
    group_results = []
    winners, runners_up, thirds_pool = {}, {}, []
    for g in T["groups"]:
        teams = [NAME_TO_CODE[t] for t in g["teams"]]
        pts = defaultdict(int); gd = defaultdict(int); gs = defaultdict(int)
        for m in g["matches"]:
            h, a = NAME_TO_CODE[m["home"]], NAME_TO_CODE[m["away"]]
            pH, pD, pA, lam_h, lam_a = ensemble_probs(ratings[h], ratings[a])
            # Modal score: round expected goals
            gh, ga = round(lam_h), round(lam_a)
            # But override winner per max(1X2). If modal says draw but pick is H/A, nudge score.
            if pH > pD and pH > pA and gh <= ga: gh = ga + 1
            elif pA > pD and pA > pH and ga <= gh: ga = gh + 1
            elif pD >= pH and pD >= pA and gh != ga:
                avg = round((lam_h + lam_a) / 2)
                gh = ga = max(1, avg)
            gs[h] += gh; gs[a] += ga
            gd[h] += gh - ga; gd[a] += ga - gh
            if gh > ga:   pts[h] += 3
            elif gh < ga: pts[a] += 3
            else:         pts[h] += 1; pts[a] += 1
            group_results.append({
                "group": g["id"], "date": m["date"],
                "home": h, "away": a, "score": f"{gh}-{ga}",
                "pH": pH, "pD": pD, "pA": pA,
            })
        standings = sorted(teams, key=lambda t: (-pts[t], -gd[t], -gs[t], -ratings[t]["fifa"]))
        rows = [{"team": t, "pts": pts[t], "gd": gd[t], "gs": gs[t]} for t in standings]
        winners[g["id"]]    = rows[0]["team"]
        runners_up[g["id"]] = rows[1]["team"]
        thirds_pool.append({**rows[2], "group_id": g["id"]})

    thirds = assign_thirds(thirds_pool, T["third_place_rules"])

    # Knockouts: pick the favorite each round
    ko_results = []
    wins = {}
    for m in T["bracket"]["r32"]:
        t1 = resolve_slot(m["slot_a"], winners, runners_up, thirds, m["id"])
        t2 = resolve_slot(m["slot_b"], winners, runners_up, thirds, m["id"])
        pH, _, pA, _, _ = ensemble_probs(ratings[t1], ratings[t2])
        winner = t1 if pH >= pA else t2
        wins[m["id"]] = winner
        ko_results.append({"round": "R32", "id": m["id"], "t1": t1, "t2": t2,
                           "p_t1": pH/(pH+pA), "winner": winner})

    for rk_label, rk_key in [("R16", "r16"), ("QF", "quarterfinals"),
                              ("SF", "semifinals")]:
        for m in T["bracket"][rk_key]:
            t1 = wins["M" + m["slot_a"][1:]]
            t2 = wins["M" + m["slot_b"][1:]]
            pH, _, pA, _, _ = ensemble_probs(ratings[t1], ratings[t2])
            winner = t1 if pH >= pA else t2
            wins[m["id"]] = winner
            ko_results.append({"round": rk_label, "id": m["id"], "t1": t1, "t2": t2,
                               "p_t1": pH/(pH+pA), "winner": winner})

    f = T["bracket"]["final"][0]
    t1 = wins["SF1"]; t2 = wins["SF2"]
    pH, _, pA, _, _ = ensemble_probs(ratings[t1], ratings[t2])
    champion = t1 if pH >= pA else t2
    ko_results.append({"round": "FINAL", "id": "FINAL", "t1": t1, "t2": t2,
                       "p_t1": pH/(pH+pA), "winner": champion})

    return {
        "group_results": group_results,
        "winners": winners, "runners_up": runners_up, "thirds": thirds,
        "ko_results": ko_results, "champion": champion,
    }


# ── per-game probabilities ──────────────────────────────────────────────────────
PER_GAME_FIELDS = [
    "stage", "group", "date", "home", "away",
    "p_home", "p_draw", "p_away", "lam_home", "lam_away", "exp_total_goals",
    "favorite", "confidence_band", "openness", "decisiveness", "character",
]


def per_game_rows(T, ratings, modal):
    """One 1X2 row per match: every group fixture (fixed) plus every knockout
    tie along the modal (most-likely) bracket. Reuses `ensemble_probs` so the
    table can never disagree with the simulation."""
    rows = []

    def make_row(stage, group_id, date, h, a, knockout):
        pH, pD, pA, lam_h, lam_a = ensemble_probs(ratings[h], ratings[a])
        char = classify_match(pH, pD, pA, lam_h, lam_a,
                              component_picks(ratings[h], ratings[a]),
                              knockout=knockout)
        fav = h if char.favorite == "home" else (a if char.favorite == "away" else "")
        return {
            "stage": stage, "group": group_id, "date": date,
            "home": h, "away": a,
            "p_home": round(pH, 4), "p_draw": round(pD, 4), "p_away": round(pA, 4),
            "lam_home": round(lam_h, 3), "lam_away": round(lam_a, 3),
            "exp_total_goals": round(lam_h + lam_a, 3),
            "favorite": fav,
            "confidence_band": char.confidence_band,
            "openness": char.openness,
            "decisiveness": char.decisiveness,
            "character": char.descriptor,
        }

    for g in T["groups"]:
        for m in g["matches"]:
            h, a = NAME_TO_CODE[m["home"]], NAME_TO_CODE[m["away"]]
            rows.append(make_row("group", g["id"], m["date"], h, a, knockout=False))

    for ko in modal["ko_results"]:
        rows.append(make_row(ko["round"], "", "", ko["t1"], ko["t2"], knockout=True))

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print("Loading ratings from DuckDB ...")
    ratings = load_ratings()
    print(f"  loaded {len(ratings)} teams")

    T = json.loads(TJ.read_text())

    print("\nComputing modal-path bracket ...")
    modal = modal_path(T, ratings)
    print(f"  modal champion: {modal['champion']}")

    print(f"\nRunning {args.n:,} Monte Carlo simulations ...")
    probs = monte_carlo(T, ratings, args.n, args.seed)
    ranked = sorted(probs.items(), key=lambda x: -x[1]["champion"])

    print("\nTop 15 (Monte Carlo champion probabilities):")
    print(f"{'Team':6} {'Win%':>6} {'Final':>7} {'Semi':>7} {'QF':>7} {'R16':>7}")
    for code, p in ranked[:15]:
        print(f"{code:6} {p['champion']*100:5.1f}% {p['final']*100:6.1f}% "
              f"{p['sf']*100:6.1f}% {p['qf']*100:6.1f}% {p['r16']*100:6.1f}%")

    # Persist outputs
    with open(OUT / "probabilities.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["team","p_champion","p_final","p_semi","p_qf","p_r16","p_r32"])
        for code, p in ranked:
            w.writerow([code, round(p["champion"],4), round(p["final"],4),
                        round(p["sf"],4), round(p["qf"],4),
                        round(p["r16"],4), round(p["r32"],4)])

    (OUT / "modal_bracket.json").write_text(json.dumps(modal, indent=2, default=str))

    pg = per_game_rows(T, ratings, modal)
    with open(OUT / "per_game.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PER_GAME_FIELDS)
        w.writeheader()
        w.writerows(pg)

    print(f"\nSaved → {OUT.relative_to(ROOT)}/probabilities.csv")
    print(f"Saved → {OUT.relative_to(ROOT)}/modal_bracket.json")
    print(f"Saved → {OUT.relative_to(ROOT)}/per_game.csv ({len(pg)} matches)")


if __name__ == "__main__":
    main()
