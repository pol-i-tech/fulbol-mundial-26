# Model Card: poisson-goals

| Field | Value |
|---|---|
| **Model name** | poisson-goals |
| **Author(s)** | Project contributors |
| **Approach** | Time-decayed independent Poisson model fit on international goals. |
| **Stack** | Python, pandas, numpy, scipy |
| **Data sources** | `martj42/international_results` |
| **Training window** | Recent international results; exact window must be consolidated into methodology docs |
| **Calibration method** | Component comparison against WC2022 research outputs |
| **Confidence reporting** | `medium` in current snapshots |
| **Update cadence** | Ad-hoc research snapshots |
| **Output location** | `results/poisson-goals/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered** | `match_1x2` |
| **Known limitations** | Goal outcomes are noisy; sparse international schedule; no xG, lineup, injury, or travel signal. |
| **Validation status** | Research component. Needs methodology consolidation and held-out metrics before actionability. |
| **Missing-player policy** | Ignores player data entirely. |
| **Stale-data policy** | Depends on latest martj42 results snapshot. |
| **Injury/suspension policy** | Ignored. |
| **Market usage boundary** | Ensemble input only; not actionable alone. |

## Subjective adjustments

| Parameter | Value | Evidence / justification |
|---|---|---|
| Match importance weights | See `DEVELOPMENT.md` | Research prior by competition type |
| Time decay | Needs consolidation | Do not change without backtest |

## Validation

No standalone held-out validation report is committed for this exact snapshot model.
