# Modeling: Elo baseline

## Mission

Maintain the World Football Elo baseline. Elo is the project's *long-term reputation prior* — the slowest-moving signal, decades of head-to-head results weighted by goal margin. It anchors the ensemble when other signals are noisy. See [`model-roles-and-best-use`](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md#model-1--elo-long-term-reputation) for what this model does and does not measure.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| eloratings.net World ratings | `https://www.eloratings.net/World.tsv` | Pulled by `tools/weekly_pull.py` |
| martj42 results history | `data/raw/martj42/latest/results.csv` | For form-corrected Elo update if used |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Predictions | `results/elo-baseline/<YYYY-MM-DD>/predictions.csv` | [8-column schema](../../DEVELOPMENT.md#prediction-output-schema) |
| Methodology code | `methodology/elo-baseline/elo.py` | TODO — currently lives inline in `tools/weekly_pull.py` |
| Model card | `results/elo-baseline/MODEL.md` | Per [model-card template](../../results/_template/MODEL.md) |
| CHANGELOG | `methodology/elo-baseline/CHANGELOG.md` | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `methodology/elo-baseline/`
- `results/elo-baseline/`
- The Elo section of `tools/weekly_pull.py` (until methodology consolidation)

**Forbidden:** modifying any other model's `methodology/<other>/` or `results/<other>/`.

## Cadence

`weekly` — Sunday cron via the Orchestrator.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails).
- Log-loss < 1.099 (better than uniform prior) — current WC2022 backtest: 1.2254 (above floor; see [model-roles doc](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md)).
- Walk-forward only; no in-sample validation.
- Any change to draw-rate calibration or goal-margin weight is a [refinement-loop](refinement-loop.md) trigger.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Ensemble](modeling-ensemble.md) | `results/elo-baseline/<date>/predictions.csv` | weekly |
| [Comparison/Edge](synthesis-comparison-edge.md) | Same | weekly |
| [Validation/Backtest](quality-validation-backtest.md) | Same; backtests on WC2022/Euro2024 | per refinement |

## Escalation

- Stop and escalate if: eloratings.net World.tsv schema changes (puller fails — intentional).
- Stop and escalate if: log-loss regresses by > 0.05 vs the previous snapshot for the same fixture window (suggests upstream Elo recompute or a data error).
- Stop and escalate if: `tools/validate_predictions.py` fails on the new snapshot.

## Verification

- New `predictions.csv` exists for the dated snapshot and passes `tools/validate_predictions.py`.
- Probabilities sum to ~1.0 per (match_id, market_type).
- Spot-check: top-tier nations (Brazil, Argentina, France) have Elo-derived win probabilities consistent with prior snapshots when fixtures are similar.

## Status

**Snapshot-producing today.** Predictions for 2026-04-28 exist. Methodology code currently lives inline in `tools/weekly_pull.py`; consolidating into `methodology/elo-baseline/` is open work and triggers the [refinement-loop protocol](refinement-loop.md) only if predictions change as a result.
