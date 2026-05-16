"""curated-poisson-luck — Poisson goals model with per-game luck factor.

Reads team features exclusively from data/wc2026.duckdb (the curated.* namespace).
Produces match-level 1X2 predictions for the WC2026 group stage and writes them
to results/curated-poisson-luck/<today>/predictions.csv.

Three building blocks the simulator (simulate.py) re-imports:

  - load_features(con) -> pandas.DataFrame
  - compute_lambdas(features_df) -> pandas.DataFrame with lambda_team, sigma_team
  - closed_form_1x2(lambda_h, sigma_h, lambda_a, sigma_a, is_neutral) -> (p_h, p_d, p_a)

The luck factor is a per-game perturbation epsilon ~ Normal(0, sigma_team) truncated
at [-2*sigma_team, +2*sigma_team]. Goals are then sampled (or analytically
marginalised) from Poisson(max(0.05, lambda_team + epsilon)).

Plan: docs/plans/2026-05-15-002-feat-curated-poisson-luck-model-plan.md
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import date
from json import load as load_json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


MODEL_VERSION = "curated-poisson-luck-xg-xga-v0.3"
ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "wc2026.duckdb"
QUERY_PATH = Path(__file__).resolve().parent / "queries" / "team_model_features.sql"
TOURNAMENT_PATH = ROOT / "data" / "wc2026" / "tournament.json"
OUT_DIR_ROOT = ROOT / "results" / "curated-poisson-luck"

# Tuning constants. Centralised so the simulator picks the same values.
HOST_BOOST = 0.25                # added to lambda_home when the home team is USA/MEX/CAN
HOST_TEAM_CODES = {"USA", "MEX", "CAN"}
LAMBDA_MAX = 4.5                 # hard cap to bound the luck-perturbed lambda
LAMBDA_FLOOR = 0.05              # minimum effective lambda fed to Poisson
SIGMA_FLOOR = 0.4                # minimum team-level goal-scoring sigma
ECON_ALPHA_GDP = 0.05            # GDP weight on the econ multiplier
ECON_ALPHA_POP = 0.02            # population weight on the econ multiplier
ECON_MULT_CLIP = (0.85, 1.15)    # multiplicative cap on the econ adjustment
N_QUAD_POINTS = 11               # sigma points used in the truncated-Normal quadrature
MAX_GOALS = 8                    # goal-distribution cutoff for the closed-form 1X2
SEED = 42

# v0.2 attacking-signal weights.
W_XG = 0.55                      # squad top-11 blended xG per 90
W_FORM = 0.30                    # recent-form lambda (goals_for_last_10 / matches)
W_FIFA = 0.15                    # self-calibrated FIFA-rank prior

# v0.3 defensive multiplier: per-match adjustment that scales the attacking
# team's lambda by the opponent's defensive quality vs cohort average.
#   factor = opponent_xga_per_90 / cohort_avg_xga
# Clipped to [1/DEFENSE_FACTOR_CAP, DEFENSE_FACTOR_CAP] so a single weak
# opponent can't blow the goal model up. 1.5 means a team's lambda can swing
# ±50% based on opponent defense.
DEFENSE_FACTOR_CAP = 1.5


# ---------------------------------------------------------------------------
# 1. Data loading
# ---------------------------------------------------------------------------

def load_features(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run the wide team-features query against the curated.* namespace."""
    sql = QUERY_PATH.read_text()
    return con.sql(sql).df()


# ---------------------------------------------------------------------------
# 2. Lambda + sigma computation
# ---------------------------------------------------------------------------

def _fifa_prior_curve(features: pd.DataFrame) -> np.ndarray:
    """Linear fit of historical_goals_for_mean ~ log10(fifa_rank), clipped to [0.6, 2.6].

    Self-calibrates to the qualifier cohort so this model auto-adapts when the
    qualifier set changes.
    """
    rank = features["fifa_rank"].fillna(100).astype(float).values
    log_rank = np.log10(np.clip(rank, 1.0, None))
    target = features["historical_goals_for_mean"].astype(float).values
    mask = np.isfinite(target)
    coefs = np.polyfit(log_rank[mask], target[mask], 1)
    fifa_lambda = np.polyval(coefs, log_rank)
    return np.clip(fifa_lambda, 0.6, 2.6)


def _econ_multiplier(features: pd.DataFrame) -> np.ndarray:
    """Small log-scaled, z-scored, clipped multiplier on lambda.

    Encodes 'rich, populous nations slightly outperform their FIFA rank'.
    Capped at [0.85, 1.15] so it never dominates.
    """
    gdp = features["gdp_per_capita_usd_latest"].astype(float).values
    pop = features["population_latest"].astype(float).values

    def _z(x: np.ndarray) -> np.ndarray:
        v = np.log10(np.where(np.isfinite(x) & (x > 0), x, np.nan))
        mu = np.nanmean(v)
        sd = np.nanstd(v) or 1.0
        z = (v - mu) / sd
        z = np.where(np.isfinite(z), z, 0.0)
        return np.clip(z, -1.0, 1.0)

    mult = 1.0 + ECON_ALPHA_GDP * _z(gdp) + ECON_ALPHA_POP * _z(pop)
    return np.clip(mult, *ECON_MULT_CLIP)


def compute_lambdas(features: pd.DataFrame) -> pd.DataFrame:
    """Blend squad xG, recent form, FIFA prior, and economics into lambda_team.

    v0.2: xG is now the primary attacking signal.

      base_lambda = W_XG * xg_lambda + W_FORM * form_lambda + W_FIFA * fifa_lambda
        xg_lambda   = top_11_blended_xg_per_90 (NULL for teams with no squad data)
        form_lambda = goals_for_last_10 / matches_last_10
        fifa_lambda = self-calibrated linear fit on FIFA rank

      Fallback when xg_lambda is NULL (re-normalised to sum to 1):
      base_lambda = (W_FORM/(W_FORM+W_FIFA)) * form_lambda
                  + (W_FIFA/(W_FORM+W_FIFA)) * fifa_lambda

      lambda_team = econ_mult * base_lambda      (clipped to [0.2, LAMBDA_MAX])
      sigma_team  = max(historical_goals_for_std, SIGMA_FLOOR)
    """
    df = features.copy()

    # --- Component lambdas ---
    xg_lambda = df["top_11_blended_xg_per_90"].astype(float)
    df["form_lambda"] = (df["goals_for_last_10"].astype(float)
                         / df["matches_last_10"].replace(0, np.nan).astype(float))
    fifa_lambda = pd.Series(_fifa_prior_curve(df), index=df.index)
    df["fifa_lambda"] = fifa_lambda

    # form_lambda may be NaN if matches_last_10 == 0; fall back to fifa_lambda
    form_lambda = df["form_lambda"].where(df["form_lambda"].notna(), fifa_lambda)

    # --- Blend ---
    base_with_xg = W_XG * xg_lambda + W_FORM * form_lambda + W_FIFA * fifa_lambda

    fallback_form_weight = W_FORM / (W_FORM + W_FIFA)
    fallback_fifa_weight = W_FIFA / (W_FORM + W_FIFA)
    base_no_xg = (fallback_form_weight * form_lambda
                  + fallback_fifa_weight * fifa_lambda)

    base_lambda = base_with_xg.where(xg_lambda.notna(), base_no_xg)

    # --- Economics multiplier (small, clipped ±15%) ---
    econ_mult = _econ_multiplier(df)
    df["econ_mult"] = econ_mult

    df["xg_lambda"]     = xg_lambda
    df["base_lambda"]   = base_lambda
    df["lambda_team"]   = np.clip(base_lambda * econ_mult, 0.2, LAMBDA_MAX)
    df["sigma_team"]    = np.maximum(df["historical_goals_for_std"].fillna(0.8), SIGMA_FLOOR)
    df["xg_used"]       = xg_lambda.notna()

    # v0.3 defensive signal: carry blended xGA per team; missing teams fall
    # back to the cohort mean (no defensive adjustment for those matches).
    xga_team = df["blended_xga_per_90"].astype(float)
    cohort_avg_xga = xga_team.mean(skipna=True)
    df["xga_team"]       = xga_team.fillna(cohort_avg_xga)
    df["cohort_avg_xga"] = cohort_avg_xga
    df["xga_used"]       = xga_team.notna()
    return df


def defensive_factor(opponent_xga: float, cohort_avg_xga: float) -> float:
    """Multiplier applied to a team's attacking lambda based on opponent xGA.

    factor > 1: opponent is leaky (high xGA) → boost attacker's lambda
    factor < 1: opponent is tight (low xGA)  → reduce attacker's lambda
    Clipped to [1/DEFENSE_FACTOR_CAP, DEFENSE_FACTOR_CAP].
    """
    if cohort_avg_xga is None or cohort_avg_xga <= 0:
        return 1.0
    factor = opponent_xga / cohort_avg_xga
    lo, hi = 1.0 / DEFENSE_FACTOR_CAP, DEFENSE_FACTOR_CAP
    return float(max(lo, min(hi, factor)))


# ---------------------------------------------------------------------------
# 3. Closed-form 1X2 with luck-factor integration
# ---------------------------------------------------------------------------

def _truncnorm_weights(sigma: float, n_points: int = N_QUAD_POINTS):
    """Sample points and weights for E[f(epsilon)] with epsilon ~ TruncN(0, sigma, ±2sigma).

    Uses simple uniform discretisation across [-2*sigma, +2*sigma] with weights
    proportional to the Normal PDF. This is good enough for 0..8-goal Poisson
    marginals — Gauss-Hermite would be more elegant but harder to truncate.
    """
    eps = np.linspace(-2.0 * sigma, 2.0 * sigma, n_points)
    pdf = np.exp(-0.5 * (eps / sigma) ** 2)
    weights = pdf / pdf.sum()
    return eps, weights


def _marginal_goal_pmf(lam: float, sigma: float) -> np.ndarray:
    """PMF over goals 0..MAX_GOALS for a single team, integrated over luck draws."""
    eps, w = _truncnorm_weights(sigma)
    lam_eff = np.clip(lam + eps, LAMBDA_FLOOR, LAMBDA_MAX)
    k = np.arange(MAX_GOALS + 1)
    # Poisson PMF: lam^k * exp(-lam) / k!
    log_k_fact = np.array([math.lgamma(i + 1) for i in k])
    log_pmf = k[None, :] * np.log(lam_eff[:, None]) - lam_eff[:, None] - log_k_fact[None, :]
    pmf_per_eps = np.exp(log_pmf)
    marginal = (w[:, None] * pmf_per_eps).sum(axis=0)
    marginal /= marginal.sum()
    return marginal


def closed_form_1x2(
    lambda_h: float, sigma_h: float,
    lambda_a: float, sigma_a: float,
    is_neutral: bool,
    is_home_host: bool = False,
    home_attack_mult: float = 1.0,
    away_attack_mult: float = 1.0,
) -> tuple[float, float, float]:
    """Return (p_home, p_draw, p_away), marginalised over luck draws.

    Home advantage: when is_neutral=False AND is_home_host=True, lambda_h gets a
    HOST_BOOST. Most WC2026 matches are neutral by default. The simulator passes
    is_home_host=True only for fixtures where the listed home team is USA/MEX/CAN.

    Defensive multipliers (v0.3): home_attack_mult and away_attack_mult scale
    each team's lambda by the opponent's defensive quality vs cohort average.
    Computed by the caller via defensive_factor(opponent_xga, cohort_avg_xga).
    Default 1.0 keeps backwards compatibility with v0.2 callers.
    """
    if not is_neutral:
        lambda_h = min(LAMBDA_MAX, lambda_h + HOST_BOOST)

    lambda_h = min(LAMBDA_MAX, lambda_h * home_attack_mult)
    lambda_a = min(LAMBDA_MAX, lambda_a * away_attack_mult)

    pmf_h = _marginal_goal_pmf(lambda_h, sigma_h)
    pmf_a = _marginal_goal_pmf(lambda_a, sigma_a)

    joint = np.outer(pmf_h, pmf_a)
    p_draw = float(np.trace(joint))
    p_home = float(np.tril(joint, -1).sum())
    p_away = float(np.triu(joint, 1).sum())

    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


# ---------------------------------------------------------------------------
# 4. Prediction writer
# ---------------------------------------------------------------------------

def _confidence_label(historical_count_home: float, historical_count_away: float) -> str:
    n_min = min(historical_count_home or 0, historical_count_away or 0)
    if n_min >= 30:
        return "high"
    if n_min >= 10:
        return "medium"
    return "low"


def _build_name_to_code(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Map tournament.json team names to FIFA3 codes via curated.dim_team.

    A small alias dict covers spelling differences the dim doesn't carry yet.
    Adding a row to db/masters/teams.csv is the long-term fix; aliasing keeps
    this model self-contained.
    """
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

    def resolve(name: str) -> str | None:
        if name in by_name:
            return by_name[name]
        if name in aliases and aliases[name] in by_name:
            return by_name[aliases[name]]
        return None
    return {"_resolve": resolve, "_table": by_name}


def write_predictions(con: duckdb.DuckDBPyConnection, lambdas: pd.DataFrame, out_dir: Path) -> Path:
    """Generate predictions.csv for every WC2026 group-stage fixture."""
    tournament = load_json(TOURNAMENT_PATH.open())
    name_resolver = _build_name_to_code(con)["_resolve"]

    by_code = lambdas.set_index("team_code")

    rows: list[dict] = []
    today = date.today().isoformat()
    unresolved: list[str] = []

    for group in tournament["groups"]:
        for match in group["matches"]:
            home_name = match["home"]
            away_name = match["away"]
            home_code = name_resolver(home_name)
            away_code = name_resolver(away_name)
            if home_code is None or away_code is None:
                unresolved.append(f"{home_name} vs {away_name}")
                continue
            if home_code not in by_code.index or away_code not in by_code.index:
                unresolved.append(f"{home_name} ({home_code}) vs {away_name} ({away_code})")
                continue

            home_row = by_code.loc[home_code]
            away_row = by_code.loc[away_code]
            is_host = home_code in HOST_TEAM_CODES
            cohort_avg_xga = float(home_row["cohort_avg_xga"])
            home_attack_mult = defensive_factor(float(away_row["xga_team"]), cohort_avg_xga)
            away_attack_mult = defensive_factor(float(home_row["xga_team"]), cohort_avg_xga)
            p_h, p_d, p_a = closed_form_1x2(
                home_row["lambda_team"], home_row["sigma_team"],
                away_row["lambda_team"], away_row["sigma_team"],
                is_neutral=not is_host,
                is_home_host=is_host,
                home_attack_mult=home_attack_mult,
                away_attack_mult=away_attack_mult,
            )

            match_id = f"WC26-{home_code}-{away_code}-{match['date']}"
            confidence = _confidence_label(home_row.get("historical_match_count"), away_row.get("historical_match_count"))
            notes = (
                f"{home_code} lam={home_row['lambda_team']:.2f} sig={home_row['sigma_team']:.2f} "
                f"def_mult={home_attack_mult:.2f} | "
                f"{away_code} lam={away_row['lambda_team']:.2f} sig={away_row['sigma_team']:.2f} "
                f"def_mult={away_attack_mult:.2f}"
                f"{' | host_boost' if is_host else ''}"
            )

            for outcome, p in [("home", p_h), ("draw", p_d), ("away", p_a)]:
                rows.append({
                    "as_of_date":   today,
                    "match_id":     match_id,
                    "market_type":  "match_1x2",
                    "outcome":      outcome,
                    "p_model":      round(p, 4),
                    "confidence":   confidence,
                    "model_version": MODEL_VERSION,
                    "notes":        notes,
                })

    if unresolved:
        raise RuntimeError(
            f"{len(unresolved)} fixtures could not resolve a team_code: {unresolved[:5]}..."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "predictions.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path


# ---------------------------------------------------------------------------
# 5. CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--out-dir", default=None,
                        help="Override the default results/curated-poisson-luck/<today>/")
    args = parser.parse_args()

    random.seed(SEED)
    np.random.seed(SEED)

    db = Path(args.db_path)
    if not db.exists():
        raise FileNotFoundError(f"DuckDB not found at {db}; run tools/build_duckdb.py first")

    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR_ROOT / date.today().isoformat()

    con = duckdb.connect(str(db), read_only=True)
    try:
        features = load_features(con)
        lambdas = compute_lambdas(features)
        out_path = write_predictions(con, lambdas, out_dir)
    finally:
        con.close()

    n_rows = sum(1 for _ in out_path.open()) - 1  # minus header
    print(f"Wrote {n_rows} prediction rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
