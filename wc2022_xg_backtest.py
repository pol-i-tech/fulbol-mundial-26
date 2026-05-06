"""
WC 2022 Backtest — xG-Patched Ensemble
Three independent models trained on pre-WC-2022 data, tested on all 64 WC 2022 matches.

Models:
  1. elo-baseline       — walk-forward Elo with goal-margin multiplier
  2. form-last-10       — avg points per game, last 10 matches per team
  3. poisson-xg         — Dixon-Coles Poisson, xG replaces goals where StatsBomb data exists
  ensemble-v2           — equal weight (33/33/33) of the three above
  ensemble-e3 (bench)   — loaded from existing file; Elo+goals-Poisson+Form blend

Output:
  Per-match comparison table (all models + ensemble + actual result)
  Summary metrics table (log-loss, accuracy, Brier per model)
  results/poisson-xg/wc2022-backtest/predictions.csv
  results/ensemble-v2/wc2022-backtest/predictions.csv
"""
import warnings, os, csv
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson, ttest_rel
from sklearn.metrics import log_loss, brier_score_loss
from pathlib import Path

ROOT    = Path(__file__).parent
DERIVED = ROOT / "data" / "derived"

# ── CONSTANTS ──────────────────────────────────────────────────────────────────
TRAIN_START  = pd.Timestamp("2012-01-01")
WC22_START   = pd.Timestamp("2022-11-20")
WC22_END     = pd.Timestamp("2022-12-18")
KO_START     = pd.Timestamp("2022-12-03")   # first R16 match

# Player-xg-poisson λ config
LAMBDA_MIN  = 0.70
LAMBDA_MAX  = 1.90
LAMBDA_BASE = 1.15  # historical avg WC goals/game

IMPORTANCE = {
    "FIFA World Cup": 1.0, "UEFA Euro": 0.9, "Copa América": 0.9,
    "AFC Asian Cup": 0.85, "Gold Cup": 0.7, "Africa Cup of Nations": 0.85,
    "FIFA World Cup qualification": 0.7, "UEFA Euro qualification": 0.65,
    "FIFA Confederations Cup": 0.8, "UEFA Nations League": 0.6,
}

def get_importance(t):
    for k, v in IMPORTANCE.items():
        if k.lower() in str(t).lower():
            return v
    return 0.35

def time_decay(date, ref, xi=0.002):
    return np.exp(-xi * (ref - date).days)


# ── DATA LOADING ───────────────────────────────────────────────────────────────
def load_martj42():
    df = pd.read_csv(ROOT / "data/raw/martj42/latest/results.csv", parse_dates=["date"])
    df = df[df["home_score"].notna()].copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    return df


def load_statsbomb_xg_training():
    """Load StatsBomb team xG for WC 2018 + Euro 2020 only (pre-WC-2022 training signal)."""
    sb = pd.read_parquet(ROOT / "data/derived/statsbomb_team_xg.parquet")
    train = sb[sb["season"].isin(["wc2018", "euro2020"])].copy()

    # Build per-match xG lookup: (home_team, away_team) -> (home_xg, away_xg)
    home_sb = train[train["is_home"] == True][["match_id","team","opponent","xg","match_date"]].copy()
    away_sb = train[train["is_home"] == False][["match_id","team","opponent","xg"]].copy()
    merged  = home_sb.merge(away_sb, on="match_id", suffixes=("_h","_a"))
    merged  = merged.rename(columns={
        "team_h":"home_team","opponent_h":"away_team",
        "xg_h":"home_xg","xg_a":"away_xg","match_date":"date"
    })
    merged["date"] = pd.to_datetime(merged["date"])
    return merged[["home_team","away_team","home_xg","away_xg","date"]]


def build_hybrid_training(martj42_df, sb_xg):
    """
    Merge StatsBomb xG into the martj42 training set.
    Where a match exists in StatsBomb, replace goals with xG.
    Falls back to actual goals for all other matches.
    """
    train = martj42_df[
        (martj42_df["date"] >= TRAIN_START) &
        (martj42_df["date"] < WC22_START)
    ].copy()

    # Build lookup key on team names (StatsBomb and martj42 share names)
    sb_lookup = {}
    for _, r in sb_xg.iterrows():
        sb_lookup[(r["home_team"], r["away_team"])] = (r["home_xg"], r["away_xg"])
        sb_lookup[(r["away_team"], r["home_team"])] = (r["away_xg"], r["home_xg"])

    xg_h, xg_a, used_xg = [], [], []
    for _, r in train.iterrows():
        key = (r["home_team"], r["away_team"])
        if key in sb_lookup:
            h, a = sb_lookup[key]
            xg_h.append(h); xg_a.append(a); used_xg.append(True)
        else:
            xg_h.append(float(r["home_score"]))
            xg_a.append(float(r["away_score"]))
            used_xg.append(False)

    train = train.copy()
    train["eff_home"] = xg_h
    train["eff_away"] = xg_a
    train["used_xg"]  = used_xg
    xg_count = sum(used_xg)
    print(f"  Hybrid training: {len(train):,} matches, {xg_count} with StatsBomb xG, "
          f"{len(train)-xg_count} with goals fallback")
    return train


# ── MODEL 1: ELO ──────────────────────────────────────────────────────────────
def build_elo(matches, k=30):
    ratings = {}
    def get_r(t): return ratings.get(t, 1500)
    for _, m in matches.sort_values("date").iterrows():
        h, a = m["home_team"], m["away_team"]
        rh, ra = get_r(h), get_r(a)
        eh = 1 / (1 + 10**((ra - rh) / 400))
        gh, ga = m["home_score"], m["away_score"]
        sh = 1.0 if gh > ga else 0.0 if gh < ga else 0.5
        gd   = abs(gh - ga)
        mult = np.log(max(gd,1)+1) * (1 if gd<=1 else 1.5 if gd==2 else 1.75)
        ratings[h] = rh + k * mult * (sh - eh)
        ratings[a] = ra + k * mult * ((1-sh) - (1-eh))
    return ratings

def elo_probs(rh, ra, ha=50):
    exp_h = 1 / (1 + 10**((ra - rh - ha) / 400))
    ph = exp_h ** 2.2
    pa = (1 - exp_h) ** 2.2
    pd = max(0, 1 - ph - pa)
    s  = ph + pd + pa
    return ph/s, pd/s, pa/s


# ── MODEL 2: FORM ─────────────────────────────────────────────────────────────
def compute_form(matches, team, ref_date, n=10):
    tm = matches[
        ((matches["home_team"]==team) | (matches["away_team"]==team)) &
        (matches["date"] < ref_date)
    ].sort_values("date").tail(n)
    if len(tm) == 0: return 0.5
    pts = []
    for _, r in tm.iterrows():
        if r["home_team"] == team:
            pts.append(3 if r["home_score"]>r["away_score"] else 1 if r["home_score"]==r["away_score"] else 0)
        else:
            pts.append(3 if r["away_score"]>r["home_score"] else 1 if r["away_score"]==r["home_score"] else 0)
    return np.mean(pts) / 3.0

def form_probs(fh, fa, base_draw=0.25):
    rh = 0.3 + 0.5 * fh
    ra = 0.3 + 0.5 * fa
    s  = rh + base_draw + ra
    return rh/s, base_draw/s, ra/s


# ── MODEL 3: xG-POISSON ────────────────────────────────────────────────────────
def fit_xg_poisson(hybrid_train, ref_date, xi=0.002):
    """Fit Dixon-Coles attack/defence using xG (or goals fallback) as the target."""
    teams = sorted(set(hybrid_train["home_team"]) | set(hybrid_train["away_team"]))
    tidx  = {t: i for i, t in enumerate(teams)}
    n     = len(teams)

    weights = np.array([
        time_decay(r["date"], ref_date, xi) * get_importance(r["tournament"])
        for _, r in hybrid_train.iterrows()
    ])

    hi = np.array([tidx[r["home_team"]] for _, r in hybrid_train.iterrows()])
    ai = np.array([tidx[r["away_team"]] for _, r in hybrid_train.iterrows()])
    gh = hybrid_train["eff_home"].values.astype(float)
    ga = hybrid_train["eff_away"].values.astype(float)

    def neg_ll(params):
        att  = np.exp(params[:n])
        defe = np.exp(params[n:2*n])
        ha   = params[2*n]
        lam_h = np.maximum(att[hi] * defe[ai] * np.exp(ha), 1e-6)
        lam_a = np.maximum(att[ai] * defe[hi], 1e-6)
        ll = weights * (gh*np.log(lam_h) - lam_h + ga*np.log(lam_a) - lam_a)
        return -ll.sum()

    x0  = np.zeros(2*n + 1)
    res = minimize(neg_ll, x0, method="L-BFGS-B", options={"maxiter":300,"ftol":1e-6})
    att  = np.exp(res.x[:n])
    defe = np.exp(res.x[n:2*n])
    ha   = res.x[2*n]
    params = {t: (att[i], defe[i]) for t, i in tidx.items()}
    return params, ha

def poisson_probs(lam_h, lam_a, max_g=8):
    ph_arr = np.array([poisson.pmf(g, lam_h) for g in range(max_g+1)])
    pa_arr = np.array([poisson.pmf(g, lam_a) for g in range(max_g+1)])
    grid   = np.outer(ph_arr, pa_arr)
    p_home = np.tril(grid, -1).sum()
    p_away = np.triu(grid, 1).sum()
    p_draw = np.diag(grid).sum()
    s = p_home + p_draw + p_away
    return p_home/s, p_draw/s, p_away/s


# ── MODEL 4: PLAYER-xG-POISSON ────────────────────────────────────────────────
# Team name aliases: martj42/StatsBomb → ratings parquet names
_NATION_ALIASES = {
    "United States": "United States",
    "USA":           "United States",
    "Iran":          "Iran",
    "IR Iran":       "Iran",
    "South Korea":   "South Korea",
    "Korea Republic":"South Korea",
}

def _norm_nation(name):
    return _NATION_ALIASES.get(name, name)

def load_player_ratings():
    """Load pre-WC2022 attack + defense ratings. Returns (attack_map, defense_map, means)."""
    att_df = pd.read_parquet(DERIVED / "team_attack_ratings_wc2022.parquet")
    def_df = pd.read_parquet(DERIVED / "team_defense_ratings_wc2022.parquet")
    attack_map  = {_norm_nation(r.nation): r.attack_rating for r in att_df.itertuples()}
    defense_map = {_norm_nation(r.nation): r.defensive_rating for r in def_df.itertuples()}
    mean_att = float(np.mean(list(attack_map.values())))
    mean_def = float(np.mean(list(defense_map.values())))
    fallback_att = float(np.quantile(list(attack_map.values()), 0.25))
    fallback_def = mean_def
    return attack_map, defense_map, mean_att, mean_def, fallback_att, fallback_def

def player_xg_probs(home, away, attack_map, defense_map,
                    mean_att, mean_def, fallback_att, fallback_def):
    """
    λ_h = BASE × (home_attack_norm × away_defense_vuln_norm)
    Multiplicative: strong attack vs weak defense → high λ.
    defense_rating = xGA conceded/90; higher = weaker defense = higher opponent λ.
    """
    h_att = attack_map.get(_norm_nation(home), fallback_att)
    a_att = attack_map.get(_norm_nation(away), fallback_att)
    h_def = defense_map.get(_norm_nation(home), fallback_def)
    a_def = defense_map.get(_norm_nation(away), fallback_def)

    lam_h = LAMBDA_BASE * (h_att / mean_att) * (a_def / mean_def)
    lam_a = LAMBDA_BASE * (a_att / mean_att) * (h_def / mean_def)
    lam_h = float(np.clip(lam_h, LAMBDA_MIN, LAMBDA_MAX))
    lam_a = float(np.clip(lam_a, LAMBDA_MIN, LAMBDA_MAX))
    return poisson_probs(lam_h, lam_a)


# ── METRICS ───────────────────────────────────────────────────────────────────
def rps(probs, actual_idx):
    """Ranked Probability Score for 3-way prediction. Lower = better. Uniform baseline ≈ 0.333."""
    f = np.array([probs[0], probs[0] + probs[1]])
    o = np.array([float(actual_idx == 0), float(actual_idx <= 1)])
    return 0.5 * np.sum((f - o) ** 2)

def mean_rps(preds_list, actuals):
    return float(np.mean([rps(p, a) for p, a in zip(preds_list, actuals)]))

def ece_score(preds_array, actuals_array, n_bins=5):
    """ECE averaged across 3 outcome classes."""
    per_class = []
    for cls in range(3):
        p = preds_array[:, cls]
        y = (actuals_array == cls).astype(float)
        bins = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            mask = (p >= bins[i]) & (p < bins[i+1])
            if mask.sum() > 0:
                ece += mask.sum() / len(p) * abs(p[mask].mean() - y[mask].mean())
        per_class.append(ece)
    return float(np.mean(per_class)), per_class

def bootstrap_ci(preds_list, actuals, n_boots=10_000, seed=42):
    """95% percentile bootstrap CI for RPS and log-loss."""
    rng  = np.random.default_rng(seed)
    arr  = np.array(preds_list)
    n    = len(actuals)
    y_oh = np.eye(3)[actuals]
    rps_b, ll_b = [], []
    for _ in range(n_boots):
        idx = rng.integers(0, n, size=n)
        rps_b.append(np.mean([rps(arr[i], actuals[i]) for i in idx]))
        ll_b.append(log_loss(y_oh[idx], arr[idx]))
    return (
        (float(np.percentile(rps_b, 2.5)), float(np.percentile(rps_b, 97.5))),
        (float(np.percentile(ll_b,  2.5)), float(np.percentile(ll_b,  97.5))),
    )

def disagreement_tier(probs_trio):
    """Classify a match by agreement across the 3 base models (elo, form, xg_p)."""
    preds = [np.argmax(p) for p in probs_trio]
    if preds[0] == preds[1] == preds[2]:
        return "golden_zone"
    counts = {0: preds.count(0), 1: preds.count(1), 2: preds.count(2)}
    max_count = max(counts.values())
    if max_count == 2:
        return "two_agree"
    return "split"


# ── PREDICT ONE MATCH ─────────────────────────────────────────────────────────
def predict_match(home, away, elo_r, xg_params, xg_ha, all_train, ref_date,
                  player_ratings=None):
    # 1) Elo (neutral venue → ha=0)
    rh, ra = elo_r.get(home, 1500), elo_r.get(away, 1500)
    e_h, e_d, e_a = elo_probs(rh, ra, ha=0)

    # 2) Form
    fh = compute_form(all_train, home, ref_date)
    fa = compute_form(all_train, away, ref_date)
    f_h, f_d, f_a = form_probs(fh, fa)

    # 3) xG-Poisson (neutral → ha=0)
    if home in xg_params and away in xg_params:
        att_h, def_h = xg_params[home]
        att_a, def_a = xg_params[away]
        lam_h = att_h * def_a          # no home advantage
        lam_a = att_a * def_h
        p_h, p_d, p_a = poisson_probs(lam_h, lam_a)
    else:
        p_h, p_d, p_a = e_h, e_d, e_a  # fallback

    # Ensemble-v2: equal weight (3 models)
    w = 1/3
    v2_h = w*e_h + w*f_h + w*p_h
    v2_d = w*e_d + w*f_d + w*p_d
    v2_a = w*e_a + w*f_a + w*p_a
    s = v2_h + v2_d + v2_a
    v2_h, v2_d, v2_a = v2_h/s, v2_d/s, v2_a/s

    # 4) Player-xG-Poisson (attack × opponent defense λ)
    if player_ratings is not None:
        att_map, def_map, m_att, m_def, fb_att, fb_def = player_ratings
        px_h, px_d, px_a = player_xg_probs(home, away, att_map, def_map,
                                            m_att, m_def, fb_att, fb_def)
    else:
        px_h, px_d, px_a = p_h, p_d, p_a  # fallback to xg_p

    # Ensemble-backtest-v3: equal weight (4 models)
    w4 = 0.25
    v3_h = w4*(e_h + f_h + p_h + px_h)
    v3_d = w4*(e_d + f_d + p_d + px_d)
    v3_a = w4*(e_a + f_a + p_a + px_a)
    s3 = v3_h + v3_d + v3_a
    v3_h, v3_d, v3_a = v3_h/s3, v3_d/s3, v3_a/s3

    return {
        "elo":    (e_h, e_d, e_a),
        "form":   (f_h, f_d, f_a),
        "xg_p":   (p_h, p_d, p_a),
        "px":     (px_h, px_d, px_a),
        "v2":     (v2_h, v2_d, v2_a),
        "v3":     (v3_h, v3_d, v3_a),
    }


# ── LOAD ENSEMBLE-E3 BENCHMARK ────────────────────────────────────────────────
def load_e3_benchmark():
    p = ROOT / "results/ensemble-e3/wc2022-backtest/predictions_vs_actual.csv"
    df = pd.read_csv(p)
    lookup = {}
    for _, r in df.iterrows():
        key = r["match"].replace(" vs ", "__")
        lookup[key] = {
            "p_home": float(r["p_home"]),
            "p_draw": float(r["p_draw"]),
            "p_away": float(r["p_away"]),
        }
    return lookup


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("WC 2022 BACKTEST — xG-Patched Ensemble")
    print("Train: 2012-01-01 → 2022-11-19  |  Test: 64 WC 2022 matches")
    print("=" * 80)

    # Load data
    all_results = load_martj42()
    sb_xg       = load_statsbomb_xg_training()

    # Build hybrid training set
    print("\n[1] Building hybrid training set...")
    hybrid_train = build_hybrid_training(all_results, sb_xg)
    # Goals-only training for Elo and Form models
    goals_train  = all_results[
        (all_results["date"] >= TRAIN_START) &
        (all_results["date"] < WC22_START)
    ].copy()

    # Fit models
    print("[2] Fitting Elo ratings...")
    elo_ratings = build_elo(goals_train)

    print("[3] Fitting xG-Poisson (Dixon-Coles)...")
    xg_params, xg_ha = fit_xg_poisson(hybrid_train, ref_date=WC22_START)
    print(f"    Home advantage parameter: {xg_ha:.3f} (set to 0 for WC neutral venue)")

    print("[4] Loading player-xG ratings (attack + defense)...")
    player_ratings = load_player_ratings()
    att_map, def_map, m_att, m_def, fb_att, fb_def = player_ratings
    print(f"    Attack: {len(att_map)} nations  |  Defense: {len(def_map)} nations")

    # WC 2022 test matches
    wc22 = all_results[
        (all_results["date"] >= WC22_START) &
        (all_results["date"] <= WC22_END) &
        (all_results["tournament"] == "FIFA World Cup")
    ].sort_values("date").reset_index(drop=True)
    print(f"[5] Test set: {len(wc22)} WC 2022 matches\n")

    # Load e3 benchmark
    e3_bench = load_e3_benchmark()

    # Run predictions
    results_table = []
    preds_elo, preds_form, preds_xgp, preds_px, preds_v2, preds_v3, preds_e3 = [], [], [], [], [], [], []
    actuals = []
    dates   = []

    for _, row in wc22.iterrows():
        home, away = row["home_team"], row["away_team"]
        gh, ga     = row["home_score"], row["away_score"]
        actual_idx = 0 if gh > ga else 1 if gh == ga else 2
        actual_lbl = "H" if gh > ga else "D" if gh == ga else "A"

        preds = predict_match(home, away, elo_ratings, xg_params, xg_ha,
                              goals_train, ref_date=row["date"],
                              player_ratings=player_ratings)

        e_h, e_d, e_a   = preds["elo"]
        f_h, f_d, f_a   = preds["form"]
        p_h, p_d, p_a   = preds["xg_p"]
        px_h, px_d, px_a = preds["px"]
        v_h, v_d, v_a   = preds["v2"]
        v3_h, v3_d, v3_a = preds["v3"]

        # e3 benchmark
        key = f"{home}__{away}"
        e3  = e3_bench.get(key, {"p_home": v_h, "p_draw": v_d, "p_away": v_a})
        b_h, b_d, b_a = e3["p_home"], e3["p_draw"], e3["p_away"]

        # Disagreement tier (3-model base: elo, form, xg_p)
        tier = disagreement_tier([(e_h,e_d,e_a), (f_h,f_d,f_a), (p_h,p_d,p_a)])

        preds_elo.append([e_h, e_d, e_a])
        preds_form.append([f_h, f_d, f_a])
        preds_xgp.append([p_h, p_d, p_a])
        preds_px.append([px_h, px_d, px_a])
        preds_v2.append([v_h, v_d, v_a])
        preds_v3.append([v3_h, v3_d, v3_a])
        preds_e3.append([b_h, b_d, b_a])
        actuals.append(actual_idx)
        dates.append(row["date"])

        v2_pred  = ["H","D","A"][np.argmax([v_h, v_d, v_a])]
        v3_pred  = ["H","D","A"][np.argmax([v3_h, v3_d, v3_a])]
        # Confidence = max probability of the predicted outcome (v3 ensemble)
        v3_conf  = max(v3_h, v3_d, v3_a)
        results_table.append({
            "date":     str(row["date"].date()),
            "match":    f"{home} vs {away}",
            "score":    f"{gh}-{ga}",
            "actual":   actual_lbl,
            "is_ko":    row["date"] >= KO_START,
            "tier":     tier,
            # elo
            "elo_H": round(e_h,3), "elo_D": round(e_d,3), "elo_A": round(e_a,3),
            "elo_pred": ["H","D","A"][np.argmax([e_h,e_d,e_a])],
            # form
            "form_H": round(f_h,3), "form_D": round(f_d,3), "form_A": round(f_a,3),
            "form_pred": ["H","D","A"][np.argmax([f_h,f_d,f_a])],
            # xg-poisson (Dixon-Coles fit)
            "xgp_H": round(p_h,3), "xgp_D": round(p_d,3), "xgp_A": round(p_a,3),
            "xgp_pred": ["H","D","A"][np.argmax([p_h,p_d,p_a])],
            # player-xg-poisson (attack × defense)
            "px_H": round(px_h,3), "px_D": round(px_d,3), "px_A": round(px_a,3),
            "px_pred": ["H","D","A"][np.argmax([px_h,px_d,px_a])],
            # ensemble-v2 (3-model)
            "v2_H": round(v_h,3), "v2_D": round(v_d,3), "v2_A": round(v_a,3),
            "v2_pred": v2_pred,
            "v2_correct": "✓" if v2_pred == actual_lbl else "✗",
            # ensemble-backtest-v3 (4-model)
            "v3_H": round(v3_h,3), "v3_D": round(v3_d,3), "v3_A": round(v3_a,3),
            "v3_pred": v3_pred,
            "v3_correct": "✓" if v3_pred == actual_lbl else "✗",
            "v3_confidence": round(v3_conf,3),
            # e3 benchmark
            "e3_H": round(b_h,3), "e3_D": round(b_d,3), "e3_A": round(b_a,3),
            "e3_pred": ["H","D","A"][np.argmax([b_h,b_d,b_a])],
        })

    # ── PRINT COMPARISON TABLE ──────────────────────────────────────────────────
    actuals_arr = np.array(actuals)
    print("=" * 140)
    print(f"{'MATCH':<30} {'SCR':>5}  {'ELO':^14}  {'FORM':^14}  {'xG-DC':^14}  {'PX-xG':^14}  {'V3-ENS':^14}  {'ACT':>3} {'TIER':>12} {'CONF':>5} {'OK':>2}")
    print(f"{'':30}  {'':5}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}")
    print("-" * 140)

    group_matches = sorted([r for r in results_table if not r["is_ko"]], key=lambda x: x["date"])
    ko_matches    = sorted([r for r in results_table if r["is_ko"]],     key=lambda x: x["date"])

    for stage_label, stage_rows in [("── GROUP STAGE (48 matches) ──", group_matches),
                                     ("── KNOCKOUT (16 matches) ──", ko_matches)]:
        print(f"\n  {stage_label}")
        for r in stage_rows:
            print(
                f"{r['match']:<30} {r['score']:>5}  "
                f"{r['elo_H']:>4.2f} {r['elo_D']:>4.2f} {r['elo_A']:>4.2f}  "
                f"{r['form_H']:>4.2f} {r['form_D']:>4.2f} {r['form_A']:>4.2f}  "
                f"{r['xgp_H']:>4.2f} {r['xgp_D']:>4.2f} {r['xgp_A']:>4.2f}  "
                f"{r['px_H']:>4.2f} {r['px_D']:>4.2f} {r['px_A']:>4.2f}  "
                f"{r['v3_H']:>4.2f} {r['v3_D']:>4.2f} {r['v3_A']:>4.2f}  "
                f"{r['actual']:>3} {r['tier']:>12} {r['v3_confidence']:>5.2f} {r['v3_correct']:>2}"
            )

    # ── SUMMARY METRICS ────────────────────────────────────────────────────────
    y_oh = np.eye(3)[actuals]

    all_preds = [
        ("elo-baseline",        preds_elo),
        ("form-last-10",        preds_form),
        ("poisson-xg (DC fit)", preds_xgp),
        ("player-xg-poisson",   preds_px),
        ("ensemble-v2 (3-mdl)", preds_v2),
        ("ens-backtest-v3",     preds_v3),
        ("ensemble-e3 (bench)", preds_e3),
    ]

    print("\n" + "=" * 90)
    print("SUMMARY METRICS — WC 2022 (64 matches)")
    print(f"  Pinnacle benchmark ≈ log-loss 0.97 | acc 47% | RPS 0.185 | uniform baseline RPS 0.333")
    print("=" * 90)
    print(f"{'Model':<28} {'Log-loss':>9} {'Acc':>7} {'Correct':>8} {'RPS':>7} {'ECE':>7}")
    print("-" * 90)

    summary_rows = []
    rps_series = {}
    ll_series  = {}
    for label, preds_list in all_preds:
        arr  = np.array(preds_list)
        ll   = log_loss(y_oh, arr)
        acc  = float(np.mean(np.argmax(arr, axis=1) == actuals_arr))
        rps_val = mean_rps(preds_list, actuals)
        ece_val, _ = ece_score(arr, actuals_arr)
        flag = ""
        row = {"model": label, "log_loss": round(ll,4), "accuracy": round(acc,3),
               "correct": int(acc*len(actuals)), "rps": round(rps_val,4),
               "ece": round(ece_val,4)}
        summary_rows.append(row)
        rps_series[label] = [rps(p, a) for p, a in zip(preds_list, actuals)]
        ll_series[label]  = [log_loss(y_oh[[i]], arr[[i]]) for i in range(len(actuals))]
        print(f"{label:<28} {ll:>9.4f} {acc:>6.1%} {int(acc*64):>5}/{len(actuals)} "
              f"{rps_val:>7.4f} {ece_val:>7.4f}")

    best_rps = min(summary_rows, key=lambda x: x["rps"])
    print(f"\n  ◄ Best RPS: {best_rps['model']} ({best_rps['rps']:.4f})")
    best_ll  = min(summary_rows, key=lambda x: x["log_loss"])
    print(f"  ◄ Best Log-loss: {best_ll['model']} ({best_ll['log_loss']:.4f})")

    # ── BOOTSTRAP CONFIDENCE INTERVALS ─────────────────────────────────────────
    print("\n── 95% Bootstrap CIs (10,000 resamples, N=64) ──")
    print(f"  Note: at N=64, differences <0.07 log-loss unlikely to reach p<0.05")
    print(f"  {'Model':<28} {'RPS CI':^22} {'Log-loss CI':^22}")
    print(f"  {'-'*70}")
    ci_rows = []
    for label, preds_list in all_preds:
        rps_ci, ll_ci = bootstrap_ci(preds_list, actuals)
        print(f"  {label:<28} [{rps_ci[0]:.4f}, {rps_ci[1]:.4f}]   [{ll_ci[0]:.4f}, {ll_ci[1]:.4f}]")
        ci_rows.append({"model": label,
                        "rps_ci_lo": rps_ci[0], "rps_ci_hi": rps_ci[1],
                        "ll_ci_lo": ll_ci[0],  "ll_ci_hi": ll_ci[1]})

    # ── PAIRED T-TEST ──────────────────────────────────────────────────────────
    print("\n── Paired t-test RPS: player-xg-poisson vs others ──")
    px_rps = rps_series["player-xg-poisson"]
    for label, _ in all_preds:
        if label == "player-xg-poisson": continue
        t, p = ttest_rel(px_rps, rps_series[label])
        direction = "PX better" if np.mean(px_rps) < np.mean(rps_series[label]) else "PX worse"
        print(f"  PX vs {label:<28} t={t:+.3f}  p={p:.3f}  ({direction})")

    # ── STAGE SPLIT ────────────────────────────────────────────────────────────
    print("\n── Stage split: Groups (N=48) vs Knockouts (N=16) ──")
    for stage_name, stage_mask_fn in [
        ("Groups   ", lambda i: not results_table[i]["is_ko"]),
        ("Knockouts", lambda i: results_table[i]["is_ko"]),
    ]:
        idx = [i for i in range(len(actuals)) if stage_mask_fn(i)]
        if not idx: continue
        stage_actuals = [actuals[i] for i in idx]
        stage_y = np.eye(3)[stage_actuals]
        print(f"\n  {stage_name} (N={len(idx)})")
        print(f"  {'Model':<28} {'Log-loss':>9} {'Acc':>7} {'RPS':>7}")
        for label, preds_list in all_preds:
            arr_s = np.array([preds_list[i] for i in idx])
            ll_s  = log_loss(stage_y, arr_s)
            acc_s = float(np.mean(np.argmax(arr_s, axis=1) == np.array(stage_actuals)))
            rps_s = mean_rps([preds_list[i] for i in idx], stage_actuals)
            print(f"  {label:<28} {ll_s:>9.4f} {acc_s:>6.1%} {rps_s:>7.4f}")

    # ── DISAGREEMENT TIER ANALYSIS ─────────────────────────────────────────────
    print("\n── Disagreement tier analysis (3-model base: elo+form+xg-DC) ──")
    tier_stats = {}
    for i, r in enumerate(results_table):
        tier = r["tier"]
        v3_pred = r["v3_pred"]
        correct = v3_pred == r["actual"]
        if tier == "golden_zone" and not correct:
            tier = "false_consensus"
        if tier not in tier_stats:
            tier_stats[tier] = {"n": 0, "correct": 0, "rps_sum": 0.0}
        tier_stats[tier]["n"] += 1
        tier_stats[tier]["correct"] += int(correct)
        tier_stats[tier]["rps_sum"] += rps(preds_v3[i], actuals[i])

    print(f"  {'Tier':<20} {'N':>4} {'Accuracy':>10} {'Avg RPS':>9}")
    print(f"  {'-'*48}")
    tier_rows = []
    for tier in ["golden_zone", "false_consensus", "two_agree", "split"]:
        if tier not in tier_stats: continue
        s = tier_stats[tier]
        acc = s["correct"] / s["n"]
        avg_rps = s["rps_sum"] / s["n"]
        print(f"  {tier:<20} {s['n']:>4} {acc:>9.1%} {avg_rps:>9.4f}")
        tier_rows.append({"tier": tier, "n": s["n"], "accuracy": round(acc,3),
                          "avg_rps": round(avg_rps,4)})

    # Golden zone comparison with v1
    gz = tier_stats.get("golden_zone", {})
    gz_n = gz.get("n", 0); gz_ok = gz.get("correct", 0)
    print(f"\n  Golden zone: {gz_ok}/{gz_n} correct (v1 baseline: 15/15)")
    fc = tier_stats.get("false_consensus", {})
    print(f"  False consensus (all agree + wrong): {fc.get('n',0)} games")

    # ── SAVE RESULTS ──────────────────────────────────────────────────────────
    for model_name, preds_list in [("poisson-xg", preds_xgp), ("ensemble-v2", preds_v2)]:
        out_dir = ROOT / f"results/{model_name}/wc2022-backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, r in enumerate(results_table):
            ph, pd_, pa = preds_list[i]
            pred_lbl = ["H","D","A"][np.argmax([ph,pd_,pa])]
            rows.append({
                "as_of_date": "2022-11-19",
                "match": r["match"], "score": r["score"],
                "p_home": round(ph,4), "p_draw": round(pd_,4), "p_away": round(pa,4),
                "pred": pred_lbl, "actual": r["actual"],
                "correct": "✓" if pred_lbl == r["actual"] else "✗",
                "model_version": model_name,
            })
        pd.DataFrame(rows).to_csv(out_dir / "predictions_vs_actual.csv", index=False)

    # Full comparison + stats CSVs
    comp_dir = ROOT / "results/comparisons/wc2022-backtest"
    comp_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results_table).to_csv(comp_dir / "all_models_v2_comparison.csv", index=False)

    summary_df = pd.DataFrame(summary_rows).merge(pd.DataFrame(ci_rows), on="model")
    summary_df.to_csv(comp_dir / "statistical_metrics_v2.csv", index=False)

    # Stage split CSV
    stage_rows_out = []
    for stage_name, stage_mask_fn in [("groups",    lambda i: not results_table[i]["is_ko"]),
                                       ("knockouts", lambda i: results_table[i]["is_ko"])]:
        idx = [i for i in range(len(actuals)) if stage_mask_fn(i)]
        stage_actuals = [actuals[i] for i in idx]
        stage_y = np.eye(3)[stage_actuals]
        for label, preds_list in all_preds:
            arr_s = np.array([preds_list[i] for i in idx])
            ll_s  = log_loss(stage_y, arr_s)
            acc_s = float(np.mean(np.argmax(arr_s, axis=1) == np.array(stage_actuals)))
            rps_s = mean_rps([preds_list[i] for i in idx], stage_actuals)
            stage_rows_out.append({"stage": stage_name, "model": label, "n": len(idx),
                                   "log_loss": round(ll_s,4), "accuracy": round(acc_s,3),
                                   "rps": round(rps_s,4)})
    pd.DataFrame(stage_rows_out).to_csv(comp_dir / "stage_split_evaluation.csv", index=False)
    pd.DataFrame(tier_rows).to_csv(comp_dir / "disagreement_tier_analysis.csv", index=False)

    print(f"\nSaved → results/comparisons/wc2022-backtest/")
    print(f"  all_models_v2_comparison.csv, statistical_metrics_v2.csv,")
    print(f"  stage_split_evaluation.csv, disagreement_tier_analysis.csv")


if __name__ == "__main__":
    main()
