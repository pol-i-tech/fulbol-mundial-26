# Model Card: compound-model

| Field | Value |
|---|---|
| **Model name** | compound-model |
| **Author(s)** | Luis Noguera (`@lnoguera`) |
| **Approach** | Statistical: time-decayed Dixon-Coles + Bivariate Poisson, fed by xG-aggregated lineup ratings, with Elo prior. Tournament outcomes via 10k-iteration Monte Carlo respecting 2026 bracket. |
| **Stack** | Python 3.12, `pandas`, `numpy`, `scipy`, `sklearn`; production package not yet consolidated |
| **Data sources** | `martj42/international_results`, eloratings.net, StatsBomb open data, Understat player xG, Kalshi/Polymarket market snapshots, future The Odds API/Pinnacle snapshots |
| **Training window** | 2018-01-01 → present (7,961 modern matches), exponential time-decay with `xi` ∈ [0.001, 0.003] |
| **Calibration method** | Walk-forward against Euro 2024, Copa America 2024, WC 2022; temperature scaling |
| **Confidence reporting** | `high` if backtest log-loss within 1.05× Pinnacle close; `medium` within 1.10×; `low` otherwise |
| **Update cadence** | Weekly pre-tournament, daily during the tournament |
| **Output location** | Intended: `results/compound-model/<YYYY-MM-DD>/predictions.csv`; current snapshots live under component model folders |
| **Markets covered (v1)** | `match_1x2`, `outright_winner`, `group_winner` |
| **Markets covered (v2)** | + `team_advances`, totals, BTTS |
| **Known limitations** | International xG is sparse; player data is incomplete and partly fuzzy matched; current player pool is not a confirmed WC2026 squad; market comparison still needs devig, liquidity filters, and Pinnacle-relative edge before actionability. |
| **Validation status** | WC 2022 backtest complete 2026-04-28 for component ensemble. ensemble-v2 log-loss 1.054 (beats ensemble-e3 1.062). Form model strongest individual predictor (46.9% accuracy). xG-Poisson needs more training data. |
| **Backtest results** | `results/comparisons/wc2022-backtest/` — per-match predictions and summary metrics |
| **Betting rule** | Research rule only until market normalization is fixed: Golden Zone, skip 3-way splits, require devigged market edge, Pinnacle-relative edge, and nonzero/liquid market volume. |
| **Plan** | [`docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md`](docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md) |
| **Model roles** | [`../docs/solutions/best-practices/model-roles-and-best-use-2026-04-28.md`](../docs/solutions/best-practices/model-roles-and-best-use-2026-04-28.md) |
| **Next priority** | Add player coverage audit and missing-player policy, then wire `team_attack_ratings.parquet` into a backtested component model. |

## Required limitations before actionability

- Missing-player policy: not yet implemented.
- Stale-data policy: not yet implemented.
- Injury/suspension policy: not yet implemented.
- Squad uncertainty: current player ratings are historical/likely pool inputs, not confirmed WC2026 squads.
- Market usage boundary: comparison/research only until devig, liquidity, and Pinnacle filters are enforced in code.
