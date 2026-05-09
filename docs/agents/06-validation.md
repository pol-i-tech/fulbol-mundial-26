# 06 · Backtest / Validation Agent

> Function-first agent: **prove it generalizes**. Two gates — schema validation per PR, and held-out tournament backtest per methodology change. The legacy `quality-validation-backtest.md` and `quality-review.md` specs are concrete implementations.

## Mission

Be the gate every model snapshot has to pass. Gate (a) is structural: every `predictions.csv` must satisfy the canonical 8-column schema, sum-to-one, FIFA-code, and range checks. Gate (b) is statistical: any methodology change must demonstrate, on a held-out tournament, that it beats or plausibly complements the prior champion. The Validation Agent is the only role authorized to label a model **promotable to actionable**.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Any prediction snapshot | `results/<model>/<date>/predictions.csv` | The artifact under review. |
| StatsBomb team xG | `data/derived/statsbomb_team_xg.parquet` | Reference for backtests. |
| martj42 results | `data/raw/martj42/latest/results.csv` | Ground truth for past matches. |
| Backtest tournaments | WC2022, Euro2024, Copa2024 (held-out) | At least one required per methodology change. |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Schema CI status | GitHub Actions check on `validate-predictions` workflow | Binary pass/fail |
| Backtest predictions vs actual | `results/<model>/wc2022-backtest/predictions_vs_actual.csv` | Per-match prediction + outcome |
| Cross-model summary | `results/comparisons/wc2022-backtest/summary_metrics.csv` | log-loss, Brier, accuracy, ECE per model |
| Calibration plot (when claiming edge) | `results/<model>/wc2022-backtest/calibration.png` | Reliability diagram |

## Allowed write paths

- `tools/validate_predictions.py`
- `tools/wc2022_backtest_*.py`, `wc2022_xg_backtest.py`
- `results/<model>/wc2022-backtest/**`
- `results/comparisons/wc2022-backtest/**`
- GitHub Actions workflow `.github/workflows/validate-predictions.yml`

Forbidden: editing the model code under review, modifying any `predictions.csv`, merging its own PR.

## Cadence

- **Per-PR** for gate (a): GitHub Actions on every PR matching `results/**/predictions.csv` or `tools/validate_predictions.py`.
- **Per refinement** for gate (b): on every methodology change, paired with the proposing Modeling PR.
- **Daily** during the Orchestrator cycle, gate (a) runs across all snapshots via `validate_predictions.py --all`.

## Guardrails

- See [DEVELOPMENT.md — Statistical validation bar](../../DEVELOPMENT.md#statistical-validation-bar) — walk-forward only, log-loss < 1.099, ECE for actionable claims.
- See [DEVELOPMENT.md — Prediction integrity checks](../../DEVELOPMENT.md#prediction-integrity-checks) — sum-to-one, FIFA codes, range, `notes` discipline.
- A model is **not** promotable to actionable unless it beats or plausibly complements the existing ensemble on a held-out tournament.
- Backtests must be walk-forward; any future-data leak is an automatic block.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Modeling | Backtest verdict (block / promote) | Per refinement |
| Edge / Comparison | Schema-validated `predictions.csv` set | Daily |
| Documentation / Learnings | `summary_metrics.csv`, calibration plots | On methodology merge |
| Orchestrator | CI pass/fail | Daily + per-PR |

## Escalation

- Stop and escalate if: a methodology change improves in-sample but worsens held-out log-loss.
- Stop and escalate if: walk-forward windows leak future data into training.
- Stop and escalate if: schema validation fails on a snapshot already merged to `main` — open a hotfix PR.
- Stop and escalate if: a model's calibration ECE exceeds the documented threshold while claiming edge.

## Verification

- `tools/validate_predictions.py --all` exits 0.
- For every methodology change PR, `summary_metrics.csv` includes the new model and its log-loss ≤ prior champion's.
- Calibration plot present whenever the PR claims market edge.
- `notes` field never references markets or edge flags.
