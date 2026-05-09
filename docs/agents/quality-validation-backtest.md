# Quality: Validation / Backtest

## Mission

Be the project's evidence layer. Every prediction snapshot, before it can be merged, must pass schema validation. Every methodology change, before it can be adopted, must produce held-out backtest evidence. This role owns both gates — `tools/validate_predictions.py` for schema and `wc2022_xg_backtest.py` (and Euro2024/Copa2024 successors) for backtests — and emits a verdict the Review role acts on.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Any model snapshot | `results/<model>/<date>/predictions.csv` | For schema validation |
| Modeling change PR | The PR diff | For backtest verdict |
| StatsBomb team xG | `data/derived/statsbomb_team_xg.parquet` | Backtest evaluation set |
| martj42 results | `data/raw/martj42/latest/results.csv` | For walk-forward training cutoffs |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Validation result | CI status on the PR; pass/fail | Binary |
| Backtest predictions | `results/<model>/wc2022-backtest/predictions_vs_actual.csv` | When triggered by refinement |
| Backtest summary | `results/comparisons/wc2022-backtest/summary_metrics.csv` | Cross-model log-loss/Brier/accuracy table |
| Verdict (in PR comment) | "ADOPT / ROLL BACK / ADOPT WITH CAVEAT" | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `results/comparisons/wc2022-backtest/`
- `results/comparisons/euro2024-backtest/` (when added)
- `results/comparisons/copa2024-backtest/` (when added)
- `wc2022_xg_backtest.py` (existing)
- `tools/validate_predictions.py` (existing)

**Forbidden:** modifying a model's `methodology/` or `results/<model>/<date>/` files. The Validation role checks; it does not produce model code.

## Cadence

- `per-PR` — schema validation runs on every PR via [`.github/workflows/validate-predictions.yml`](../../.github/workflows/validate-predictions.yml).
- `per-refinement` — backtest verdict runs whenever a Modeling role triggers the [refinement-loop](refinement-loop.md).

## Guardrails

- See [DEVELOPMENT.md — Statistical validation bar](../../DEVELOPMENT.md#statistical-validation-bar).
- Walk-forward only — training window must end before the held-out tournament begins.
- **A change motivated by tournament X may not be backtested on tournament X.** This is the hardest rule from the subjectivity policy.
- Log-loss must beat uniform prior (< 1.099) for 3-outcome markets.
- ECE must not regress for any model claiming edge against markets.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Review](quality-review.md) | Verdict on the PR | per-PR |
| Modeling role triggering the change | Verdict drives ADOPT/ROLL BACK decision | per-refinement |
| [Documentation/Learnings](synthesis-documentation-learnings.md) | Backtest summary for the trend log | per refinement |

## Escalation

- Stop and escalate if: a refinement PR passes the validator but the held-out backtest has not been re-run since the last methodology change.
- Stop and escalate if: a backtest claims improvement on the same tournament cited in the hypothesis (refinement-loop violation — close the PR).
- Stop and escalate if: `validate_predictions.py` produces a false-positive failure (schema in `DEVELOPMENT.md` and the validator code disagree — fix the validator, then continue).

## Verification

- For each PR touching `results/<model>/<date>/predictions.csv`: validation CI is green.
- For each refinement PR: a CHANGELOG row exists, baseline + new metrics are recorded, and the held-out tournament differs from the motivating one.
- Backtest summary in `results/comparisons/` reflects the latest model versions.
