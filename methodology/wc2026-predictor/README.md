# wc2026-predictor

Poisson goals model with a per-game **luck factor**, built entirely off the `curated.*` namespace in `data/wc2026.duckdb`. No parquet reads, no manual data entry, no HTTP fetches.

## How to run

```bash
# Match-level 1X2 for the 72 group-stage fixtures
python3 methodology/wc2026-predictor/model.py

# Tournament Monte Carlo (default n=10000, seed=42)
python3 methodology/wc2026-predictor/simulate.py
```

Both write to `results/wc2026-predictor/<today>/`.

## What this model uses

| Source | What from it |
|---|---|
| `curated.fact_international_match` | Per-team `goals_for_mean`, `goals_for_std`, `goals_against_mean`, `goals_against_std` since 2022-01-01, tier-weighted. |
| `curated.dim_team_recent_form` | Last-10 `goals_for`, `matches`, form points. |
| `curated.dim_team_current` | Current FIFA rank + points (shrinkage prior), latest GDP per capita and population (econ multiplier). |
| `curated.fact_team_economics`, `curated.fact_team_fifa_ranking` | Read indirectly via `dim_team_current`. |
| `data/wc2026/tournament.json` | Bracket structure and group fixtures. |

The two SQL queries that load everything live in [`queries/`](queries/) — `team_goal_stats.sql` (per-team mean/std) and `team_model_features.sql` (wide model-input table joining everything per WC2026 qualifier).

## The luck factor

For each simulated match, each team draws an independent perturbation:

```
ε ~ Normal(0, σ_team)         # σ_team is that team's tier-weighted goals-scored std-dev
ε ← clip(ε, -2σ_team, +2σ_team)
λ_eff = clip(λ_team + ε, 0.05, 4.5)
goals ~ Poisson(λ_eff)
```

This models "good day / bad day" variance beyond what raw Poisson can express (Poisson has variance = mean, which is usually too tight for international football). The truncation at ±2σ keeps freak draws bounded.

The closed-form 1X2 in `model.py` integrates over the same truncated-Normal perturbation by numerical quadrature (11 sigma points per team), then computes the joint goal distribution and sums to (home, draw, away).

## How `λ_team` is built

```
form_λ           = goals_for_last_10 / matches_last_10
hist_λ           = tier-weighted goals_for_mean since 2022-01-01
fifa_λ           = self-calibrated linear fit (historical_goals_for_mean ~ log10(fifa_rank)), clipped [0.6, 2.6]

w_form           = matches_last_10 / 10                              (capped at 1.0)
w_data           = historical_match_count / 30                       (capped at 1.0)
econ_mult        = 1 + 0.05·z(log10 GDP) + 0.02·z(log10 pop)         (z clipped at ±1, total clipped [0.85, 1.15])

data_λ           = w_form · form_λ + (1 - w_form) · hist_λ
base_λ           = w_data · data_λ + (1 - w_data) · fifa_λ
λ_team           = clip(base_λ · econ_mult, 0.2, 4.5)

σ_team           = max(historical_goals_for_std, 0.4)
```

Host nations (USA, MEX, CAN) get a `+0.25` boost on `λ_home` when they're the listed home side.

## Calibration status

`pending_backtest`. The WC2022 held-out backtest is required before this model is ensembled in or treated as actionable. See the [MODEL.md card](../../results/wc2026-predictor/MODEL.md) for full validation policy.

The luck factor *deliberately* widens goal distributions, which softens favorites' `p_home` compared to pure Poisson. Whether that's a win or a loss against market-implied prices is exactly what the backtest will tell us.

## Known limitations

- FIFA ranking is a single snapshot — no temporal join on `match_date`.
- Recent-form saturates at 10 matches — hot/cold streaks can dominate the FIFA prior.
- No player-level inputs (xG, lineups, injuries) — team-level only.
- Independent Poisson — no Dixon-Coles correlation correction in v1.

## Plan

[`docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md`](../../docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md)
