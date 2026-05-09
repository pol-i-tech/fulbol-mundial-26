# Modeling: xG-Poisson

## Mission

Maintain the xG-driven Dixon-Coles model — uses expected goals (xG) from StatsBomb as the Poisson target instead of actual goals. Per [`model-roles-and-best-use`](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md#model-3--xg-poisson-underlying-quality), this is the **underlying quality** signal: identifies teams whose results don't reflect their actual performance. Aggressive in extreme cases (Brazil 95% vs Switzerland) and the model with the most upside as more xG training data lands.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| StatsBomb team xG | `data/derived/statsbomb_team_xg.parquet` | Currently 115 matches (WC2018 + Euro2020) |
| StatsBomb player xG | `data/derived/statsbomb_player_xg.parquet` | For player-level overlay |
| Time-decay xi | `[0.001, 0.003]` | Same range as `poisson-goals` |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Predictions | `results/poisson-xg/<YYYY-MM-DD>/predictions.csv` | [8-column schema](../../DEVELOPMENT.md#prediction-output-schema) |
| Backtest predictions | `results/poisson-xg/wc2022-backtest/predictions_vs_actual.csv` | Reproduced by `wc2022_xg_backtest.py` |
| Methodology code | `methodology/poisson-xg/poisson_xg.py` | TODO |
| Model card | `results/poisson-xg/MODEL.md` | Per [template](../../results/_template/MODEL.md) |
| CHANGELOG | `methodology/poisson-xg/CHANGELOG.md` | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `methodology/poisson-xg/`
- `results/poisson-xg/`
- `wc2022_xg_backtest.py` (the existing repo-root backtest script)

## Cadence

`weekly` — Sunday cron via the Orchestrator (once consolidated). Today the snapshot is produced by `wc2022_xg_backtest.py` for the held-out tournament.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails).
- Log-loss < 1.099 — current WC2022 backtest: 1.1688.
- Bayesian shrinkage for low-minutes xG outliers is **already a documented subjective adjustment** (see commit `01b6bbd`) — `MIN_RELIABLE_MINS=180`, `PRIOR_MINS=500`, `PRIOR_XG90=0.15`. Listed in `MODEL.md`. Any change to these triggers [refinement-loop](refinement-loop.md).
- Known weakness: small training sample. Adding xG from Nations League and WC qualifying is the [highest-impact P0/P1 work](data-gaps-roadmap.md#layer-3--national-recent-usage) — closes the 6-pt accuracy gap to Form.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Ensemble](modeling-ensemble.md) | `results/poisson-xg/<date>/predictions.csv` | weekly |
| [Compound-model](modeling-compound-model.md) | `statsbomb_team_xg.parquet` joined with own player ratings | weekly |
| [Comparison/Edge](synthesis-comparison-edge.md) | Snapshot | weekly |

## Escalation

- Stop and escalate if: a previously-stable team's xG-derived prediction shifts by > 15 percentage points week-over-week with no new fixture data.
- Stop and escalate if: shrinkage parameters are changed without a CHANGELOG entry.
- Stop and escalate if: backtest log-loss regresses > 0.05 vs the documented 1.1688.

## Verification

- New snapshot passes the validator.
- Backtest log-loss matches or beats the documented 1.1688 on WC2022.
- Spot-check: extreme matchups (Brazil vs minnow) still produce highly skewed but not pathological probabilities (cap at ~95%).

## Status

**Snapshot-producing via backtest today.** Production snapshot pipeline (current-match predictions) consolidation is open work — see [DEVELOPMENT.md priority stack](../../DEVELOPMENT.md#current-priority-stack) item 4.
