# Model Card: wc2026-predictor

| Field | Value |
|---|---|
| **Model name** | wc2026-predictor |
| **Author(s)** | Project contributors |
| **Approach** | Poisson goals model with a per-game luck factor. Per-team `λ_team` blends recent form, tier-weighted historical goals (since 2022), a FIFA-rank shrinkage prior, and a small log-scaled economics multiplier (GDP per capita + population). Each simulated match draws a luck perturbation `ε ~ Normal(0, σ_team)` truncated to `[-2σ, +2σ]` per team; goals sampled `Poisson(max(0.05, λ_team + ε))`. Closed-form 1X2 probabilities marginalise the same perturbation by numerical quadrature. |
| **Stack** | Python 3, DuckDB, pandas, numpy |
| **Data sources** | `curated.fact_international_match`, `curated.fact_team_economics`, `curated.fact_team_fifa_ranking`, `curated.dim_team_recent_form`, `curated.dim_team_current` — all in `data/wc2026.duckdb`. **No parquet, CSV, or HTTP reads at runtime.** |
| **Training window** | International matches since 2022-01-01 (tier-weighted for `λ_team` and `σ_team`); current FIFA snapshot for the shrinkage prior; latest reported World Bank GDP + population per country. |
| **Calibration method** | FIFA-rank → expected-goals curve is self-calibrated by linear fit (`hist_gf_mean ~ log10(fifa_rank)`) over the 48-qualifier cohort. Economics multiplier is z-scored within the cohort, clipped at ±1σ, and capped at [0.85, 1.15] on `λ_team`. |
| **Confidence reporting** | Per-fixture: `high` when both teams have ≥30 matches since 2022; `medium` when both ≥10; else `low`. |
| **Update cadence** | Re-run on every DuckDB rebuild that refreshes `fact_international_match` or `fact_team_fifa_ranking`. |
| **Output location** | `results/wc2026-predictor/<YYYY-MM-DD>/predictions.csv` (group-stage 1X2) + `results/wc2026-predictor/<YYYY-MM-DD>/probabilities.csv` (tournament Monte Carlo). |
| **Markets covered** | `match_1x2` (group stage closed-form); per-team stage-reach probabilities from 10,000 Monte Carlo tournament runs. |
| **Known limitations** | (a) FIFA-rank fact is a single snapshot — strength-of-schedule and prior reflect today, not match dates. (b) The luck factor widens distributions vs. pure Poisson, so favorites' `p_home` is meaningfully softer than market-implied prices — confirmed via WC2022 backtest is required before treating numbers as actionable. (c) No xG, lineup, injury, or travel signal. (d) Recent-form weight saturates at 10 matches; teams on a hot or cold streak dominate their FIFA prior. (e) `σ_team` floored at 0.4 for the small set of teams whose historical std-dev would otherwise be degenerate. |
| **Validation status** | `pending_backtest`. WC2022 held-out backtest is required and tracked separately. Not safe to ensemble in until backtest log-loss is competitive with `ensemble-v2` (1.054). |
| **Missing-player policy** | Ignores player data entirely. Uses team-level features only. |
| **Stale-data policy** | Depends on the most recent DuckDB rebuild. The `fifa_snapshot_date` and `economics_year` columns in the input features make staleness explicit. |
| **Injury/suspension policy** | Ignored. |
| **Market usage boundary** | Research component until WC2022 backtest lands. Not actionable alone; not yet weighted into any ensemble. |

## Subjective adjustments

| Parameter | Value | Evidence / justification |
|---|---|---|
| Tier weights for form/historical aggregation | 1.0 / 0.9 / 0.7 / 0.4 | Mirrors `ensemble_model.py:IMPORTANCE` for cross-model consistency. |
| Host boost (USA / MEX / CAN at home) | +0.25 on `λ_home` | Modest, in the range of typical home-advantage observed in international football; only applied when the listed home team is actually a host nation. |
| `σ_team` floor | 0.4 | Prevents degenerate truncated-Normal draws for teams with low historical variance. |
| `λ_team` clip range | [0.2, 4.5] | Bounds the luck-perturbed lambda to a realistic football scoring range. |
| Economics weights (GDP / population) | 0.05 / 0.02 | Z-scored, clipped at ±1σ; multiplier capped at [0.85, 1.15]. Small by design — economics is a structural prior, not a primary driver. |
| Recent-form saturation | `min(1.0, matches_last_10 / 10)` | A team with a full last-10 trusts form fully; thin samples get pulled toward the historical mean. |
| Data-vs-prior shrinkage | `min(1.0, hist_n_matches / 30)` | 30+ matches since 2022 → ignore FIFA prior; 0 matches → rely on it entirely. |

## Validation

Pending. The WC2022 held-out backtest (deferred per the plan) should report per-match log-loss, Brier score, and accuracy against actual outcomes, alongside an estimate of how much the luck factor improves or degrades calibration relative to a pure-Poisson baseline.

## Reproduction

```
# Match-level predictions (closed-form 1X2 for the 72 group-stage fixtures)
python3 methodology/wc2026-predictor/model.py

# Tournament Monte Carlo (default n=10000, seed=42)
python3 methodology/wc2026-predictor/simulate.py
```

Both scripts read only from `data/wc2026.duckdb` (curated namespace). No HTTP fetches, no parquet reads.

## Plan

[`docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md`](../../docs/plans/2026-05-15-002-feat-wc2026-predictor-model-plan.md)
