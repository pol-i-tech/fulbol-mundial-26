# Modeling: Ensemble

## Mission

Produce the calibrated final probability used for edge calculation: equal-weight blend of Elo, Form, and Poisson-xG. Per [`model-roles-and-best-use`](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md#ensemble-v2-the-calibrated-bet-sizing-number), the ensemble has the best log-loss of any single number (1.054 on WC2022) because it smooths each model's individual failure modes. **This is the number that goes into `edge = p_model - p_market_devigged`.**

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Elo predictions | `results/elo-baseline/<date>/predictions.csv` | Required |
| Form predictions | `results/form-last-10/<date>/predictions.csv` | Required |
| xG-Poisson predictions | `results/poisson-xg/<date>/predictions.csv` | Required for `ensemble-v2`; `ensemble-e3` uses `poisson-goals` instead |
| Blend weights | Equal weight 0.333/0.333/0.333 (`ensemble-v2`) | Subjective adjustment per `MODEL.md` |

## Outputs

| Output | Path | Schema |
|---|---|---|
| ensemble-v2 predictions | `results/ensemble-v2/<YYYY-MM-DD>/predictions.csv` | [8-column](../../DEVELOPMENT.md#prediction-output-schema); xG-flavored ensemble |
| ensemble-e3 predictions | `results/ensemble-e3/<YYYY-MM-DD>/predictions.csv` | 8-column; goals-flavored ensemble |
| Backtest | `results/ensemble-v2/wc2022-backtest/predictions_vs_actual.csv` | Reproduced by `wc2022_xg_backtest.py` |
| Methodology code | `methodology/ensemble/ensemble.py` | TODO; consolidate from `ensemble_model.py` |
| Model card | `results/ensemble-v2/MODEL.md`, `results/ensemble-e3/MODEL.md` | Per [template](../../results/_template/MODEL.md) |
| CHANGELOG | `methodology/ensemble/CHANGELOG.md` | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `methodology/ensemble/`
- `results/ensemble-v2/`
- `results/ensemble-e3/`
- `ensemble_model.py` (existing root-level script; consolidate into methodology folder)

## Cadence

`weekly` — Sunday cron via the Orchestrator. Runs *after* all three input models have produced same-date snapshots.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails).
- Log-loss < 1.099 — current WC2022 backtest: 1.054 (best single number).
- Blend weights are a subjective adjustment. Switching from equal-weight to a learned meta-model triggers [refinement-loop](refinement-loop.md). The model-roles doc explicitly defers meta-model work until after WC2026 backtest evidence accrues.
- **Disagreement check is required before any "actionable" flag** — see [WC2022 disagreement learning](../solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md). 3-way splits (~33/33/33) must be skipped, not bet.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Comparison/Edge](synthesis-comparison-edge.md) | `results/ensemble-v2/<date>/predictions.csv` | weekly |
| [Compound-model](modeling-compound-model.md) | Same; compound-model wraps the ensemble | weekly |

## Escalation

- Stop and escalate if: any input model snapshot is missing for the target date — the ensemble must not silently drop a model.
- Stop and escalate if: input snapshots disagree on `as_of_date` or `match_id` set.
- Stop and escalate if: validation fails on the ensemble output.

## Verification

- Output passes the validator.
- For each (match_id, market_type, outcome), `p_model` equals the equal-weight average of the three inputs (within rounding).
- Backtest log-loss on WC2022 ≤ 1.054 (the documented baseline).
- Disagreement classification reproducible — see disagreement taxonomy in the linked learning doc.

## Status

**Snapshot-producing today.** `ensemble-e3` and `ensemble-v2` both exist. Methodology consolidation into `methodology/ensemble/` is open work and may be done as one PR (both ensembles share most code).
