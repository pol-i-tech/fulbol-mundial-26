# Model Card: elo-baseline

| Field | Value |
|---|---|
| **Model name** | elo-baseline |
| **Author(s)** | Project contributors |
| **Approach** | World Football Elo baseline converted to 1X2 probabilities with a simple draw model and host-country home adjustment. Outright probabilities are a placeholder softmax over top Elo teams. |
| **Stack** | Python standard library in `tools/weekly_pull.py` |
| **Data sources** | eloratings.net `World.tsv`; `martj42/international_results` fixtures |
| **Training window** | External Elo source defines rating history; fixture pull uses current martj42 data |
| **Calibration method** | Research baseline only; no standalone calibration report committed |
| **Confidence reporting** | `low` for all rows |
| **Update cadence** | Weekly or ad-hoc via `python3 tools/weekly_pull.py <YYYY-MM-DD>` |
| **Output location** | `results/elo-baseline/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered** | `match_1x2`, placeholder `outright_winner` |
| **Known limitations** | Draw model is heuristic; team mapping is manually maintained; outright market is not a tournament simulation; no squad/player information. |
| **Validation status** | Component baseline. Must not be treated as actionable alone. |
| **Missing-player policy** | Ignores player data entirely. |
| **Stale-data policy** | Depends on freshness of pulled Elo snapshot. |
| **Injury/suspension policy** | Ignored. |
| **Market usage boundary** | Comparison only. |

## Subjective adjustments

| Parameter | Value | Evidence / justification |
|---|---|---|
| Host home adjustment | +65 Elo points for USA/MEX/CAN home-host matches | Heuristic in `tools/weekly_pull.py`; must be backtested before actionability |
| Draw floor | 0.15 | Heuristic to avoid unrealistically low draw probabilities |

## Validation

No standalone held-out validation report is committed for this component.
