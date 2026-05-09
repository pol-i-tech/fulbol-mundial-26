# Modeling: Form-last-10

## Mission

Maintain the recent-form signal: average points per game across the most recent 10 competitive fixtures, normalized to [0, 1]. This is the project's *current momentum* signal and — per [`model-roles-and-best-use`](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md#model-2--form-last-10-current-momentum) — the single strongest predictor of WC results in the WC2022 backtest (46.9% accuracy, matching Pinnacle).

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| martj42 results history | `data/raw/martj42/latest/results.csv` | Required — Form is computed from results only |
| Match importance weights | `WC=1.0, Euro/Copa=0.9, WCQ=0.7, Nations League=0.6, friendly=0.35` | See [DEVELOPMENT.md](../../DEVELOPMENT.md#match-importance-weights-recency-decay) |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Predictions | `results/form-last-10/<YYYY-MM-DD>/predictions.csv` | [8-column schema](../../DEVELOPMENT.md#prediction-output-schema) |
| Methodology code | `methodology/form-last-10/form.py` | TODO — currently outside the `methodology/` tree |
| Model card | `results/form-last-10/MODEL.md` | Per [template](../../results/_template/MODEL.md) |
| CHANGELOG | `methodology/form-last-10/CHANGELOG.md` | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `methodology/form-last-10/`
- `results/form-last-10/`

## Cadence

`weekly` — Sunday cron via the Orchestrator.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails).
- Log-loss < 1.099 — current WC2022 backtest: 1.0807. Best single-model accuracy.
- Walk-forward only.
- Any change to the importance-weight scheme is a refinement-loop trigger.
- Known weakness: schedule quality is uniform — a 10/10 run against Caribbean minnows looks identical to a 10/10 run against UEFA-A sides. See [model-roles doc](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md#model-2--form-last-10-current-momentum) for the design note on adding opponent-quality weighting.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Ensemble](modeling-ensemble.md) | `results/form-last-10/<date>/predictions.csv` | weekly |
| [Comparison/Edge](synthesis-comparison-edge.md) | Same | weekly |
| [Validation/Backtest](quality-validation-backtest.md) | Same | per refinement |

## Escalation

- Stop and escalate if: martj42 input is stale > 2 weeks.
- Stop and escalate if: any team has < 5 competitive fixtures in the lookback window — the model should label these `low` confidence, not silently extrapolate.
- Stop and escalate if: validation fails.

## Verification

- New `predictions.csv` exists for the snapshot date and passes the validator.
- Per-team form score in [0, 1].
- Spot-check: a team that won its last 5 fixtures has a meaningfully higher form score than one that lost its last 5.

## Status

**Snapshot-producing today.** Snapshot for 2026-04-28 exists in `results/form-last-10/`. Methodology consolidation into `methodology/form-last-10/` is open work.
