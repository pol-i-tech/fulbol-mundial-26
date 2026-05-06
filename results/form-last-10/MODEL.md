# Model Card: form-last-10

| Field | Value |
|---|---|
| **Model name** | form-last-10 |
| **Author(s)** | Project contributors |
| **Approach** | Recent-form model using a team's latest match results as a momentum signal. |
| **Stack** | Python / pandas in project research scripts |
| **Data sources** | `martj42/international_results` |
| **Training window** | Rolling recent-match window before prediction date |
| **Calibration method** | WC2022 component backtest in `results/comparisons/wc2022-backtest/summary_metrics.csv` |
| **Confidence reporting** | `medium` in current snapshots |
| **Update cadence** | Ad-hoc research snapshots |
| **Output location** | `results/form-last-10/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered** | `match_1x2` |
| **Known limitations** | Schedule strength is weakly modeled; squad rotation and opponent quality can distort form; no player availability signal. |
| **Validation status** | WC2022 component validation exists. Needs methodology consolidation before new snapshots are accepted. |
| **Missing-player policy** | Ignores player data entirely. |
| **Stale-data policy** | Depends on latest martj42 results snapshot. |
| **Injury/suspension policy** | Ignored. |
| **Market usage boundary** | Ensemble input only; not actionable alone. |

## Subjective adjustments

| Parameter | Value | Evidence / justification |
|---|---|---|
| Recent window | Last 10 matches | Research heuristic; documented in WC2022 backtest notes |
| Base draw probability | 0.25 in backtest implementation | Heuristic; must be revalidated if changed |

## Validation

| Backtest | Log-loss | Brier | Accuracy | Notes |
|---|---:|---:|---:|---|
| WC2022 | 1.0807 | See `summary_metrics.csv` | 46.9% | Best individual accuracy in component backtest |
