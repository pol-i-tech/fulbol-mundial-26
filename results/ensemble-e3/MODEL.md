# Model Card: ensemble-e3

| Field | Value |
|---|---|
| **Model name** | ensemble-e3 |
| **Author(s)** | Project contributors |
| **Approach** | Weighted blend of Elo, goals-Poisson, and recent Form. |
| **Stack** | Python, pandas, numpy, scipy, sklearn |
| **Data sources** | `martj42/international_results`; component model outputs |
| **Training window** | Pre-WC2022 for backtest; 2026 snapshot methodology needs consolidation |
| **Calibration method** | WC2022 backtest in `results/ensemble-e3/wc2022-backtest/` |
| **Confidence reporting** | `medium` in current snapshots |
| **Update cadence** | Ad-hoc research snapshots |
| **Output location** | `results/ensemble-e3/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered** | `match_1x2` |
| **Known limitations** | Uses goals-Poisson rather than xG-Poisson; methodology currently lives in root scripts instead of `methodology/`; no player availability signal. |
| **Validation status** | WC2022 backtest exists, but ensemble-v2 supersedes it on log-loss. |
| **Missing-player policy** | Ignores player data entirely. |
| **Stale-data policy** | Depends on component data freshness. |
| **Injury/suspension policy** | Ignored. |
| **Market usage boundary** | Comparison/research only. |

## Subjective adjustments

| Parameter | Value | Evidence / justification |
|---|---|---|
| Elo weight | 0.35 | Research blend in `ensemble_model.py` |
| Poisson weight | 0.45 | Research blend in `ensemble_model.py` |
| Form weight | 0.20 | Research blend in `ensemble_model.py` |

## Validation

| Backtest | Log-loss | Brier | Accuracy | Notes |
|---|---:|---:|---:|---|
| WC2022 | 1.0620 | See `summary_metrics.csv` | 35.9% | Superseded by xG-patched ensemble-v2 on log-loss |
