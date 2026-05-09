# Modeling: Poisson-goals

## Mission

Maintain the time-decayed goals-Poisson signal: a Dixon-Coles model fit on actual goal counts (not xG) with exponential time decay on past matches. This is the goals-only counterpart to the xG-Poisson model — useful as a robustness check and as a backstop for matchups where xG data is sparse.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| martj42 results history | `data/raw/martj42/latest/results.csv` | Required |
| Time-decay parameter `xi` | Currently in `[0.001, 0.003]` range — see [DEVELOPMENT.md](../../DEVELOPMENT.md#model-pipeline-compound-model) |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Predictions | `results/poisson-goals/<YYYY-MM-DD>/predictions.csv` | [8-column schema](../../DEVELOPMENT.md#prediction-output-schema) |
| Methodology code | `methodology/poisson-goals/poisson.py` | TODO |
| Model card | `results/poisson-goals/MODEL.md` | Per [template](../../results/_template/MODEL.md) |
| CHANGELOG | `methodology/poisson-goals/CHANGELOG.md` | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `methodology/poisson-goals/`
- `results/poisson-goals/`

## Cadence

`weekly` — Sunday cron via the Orchestrator.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails).
- Log-loss < 1.099 — current WC2022 backtest is approximate; precise figure tracked in `MODEL.md` once consolidated.
- The Dixon-Coles low-score correction (rho parameter) is a subjective adjustment and must be documented in `MODEL.md` and any change must follow [refinement-loop](refinement-loop.md).
- Any change to `xi` triggers refinement-loop.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Ensemble](modeling-ensemble.md) | `results/poisson-goals/<date>/predictions.csv` | weekly |
| [Comparison/Edge](synthesis-comparison-edge.md) | Same | weekly |

## Escalation

- Stop and escalate if: Dixon-Coles MLE fails to converge on the current data window.
- Stop and escalate if: a team's expected-goals exceed 5.0 for a single fixture (suggests fitting noise or a data error, not a real prediction).
- Stop and escalate if: validation fails.

## Verification

- New `predictions.csv` exists and passes the validator.
- Probabilities sum to ~1.0 per (match_id, market_type).
- Predicted home goals + away goals for an average matchup is in the 2.0-3.0 range (international football norm).

## Status

**Snapshot-producing today.** Snapshot for 2026-04-28 exists. Methodology consolidation pending.
