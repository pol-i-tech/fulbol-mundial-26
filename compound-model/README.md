# compound-model

A planned production wrapper for the WC 2026 prediction workbench. The repo already contains several research/model snapshots (`elo-baseline`, `form-last-10`, `poisson-goals`, `ensemble-e3`) plus a WC 2022 xG-patched backtest. This folder now describes the intended consolidated compound model, not a runnable package.

> This is **one model** in the multi-contributor [fulbol-mundial-26](../README.md) repo. See the root README for how to add your own.

## Intended Model

- Time-decayed international results model from `martj42/international_results`.
- Elo and recent-form priors.
- xG-Poisson signal from StatsBomb tournament data.
- Player/squad attack signal from `data/derived/squad_xg_ratings.parquet` and `team_attack_ratings.parquet`.
- Market comparison against Kalshi, Polymarket, and Pinnacle/Hard Rock via The Odds API once devigging and liquidity filters are implemented.
- Tournament simulation only after the base match probabilities and player-data coverage pass validation.

## Status

**Research pieces exist; production consolidation is pending.** The older full plan is at [`docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md`](docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md), but the active guardrails now live in [`../DEVELOPMENT.md`](../DEVELOPMENT.md).

| Phase | Target | Status |
|---|---|---|
| Phase 0: Guardrails | now | Validator added; methodology/model-card consolidation still needed |
| Phase 1: Market comparison correctness | next | Devig, min-volume, and Pinnacle edge filters need implementation |
| Phase 2: Player data coverage | next | Coverage report, name overrides, missing-player policy needed |
| Phase 3: Consolidated model | after Phase 1-2 | Move research logic into reproducible methodology folders |
| Phase 4: Tournament simulation | later | Defer until match-level probabilities pass backtests |

## Cost and credentials

**$0/month for live operation.** One optional $30 charge for The Odds API historical-odds backtest.

| Source | Cost | Credential |
|---|---|---|
| The Odds API (Hard Rock + Pinnacle) | $0/mo free tier | API key (free signup) |
| Kalshi (reads only — verified unauthenticated) | Free | None at v1 |
| Polymarket Gamma | Free | None |
| eloratings.net / StatsBomb / `martj42` / Understat | Free | None |
| Hosting / DB / scheduler | $0 | Your laptop |

See the plan's "Cost & credentials" decision and the validation findings section for details.

## Current Useful Commands

```bash
python3 tools/validate_predictions.py --all
python3 wc2022_xg_backtest.py
python3 tools/weekly_pull.py 2026-04-28
```

There is not yet a `uv run wc26 weekly` CLI in this repo. Do not document or build dashboards around that command until the production package exists.

## Why this approach

International football is data-sparse — most teams play 8–12 competitive matches per cycle. Pure goal-based Poisson models on national-team data overfit. The pipeline leans on three pillars instead:

1. **Goal-based time-decayed Dixon-Coles** trained on 7,961 modern (2018+) internationals
2. **Club-xG-aggregated lineup ratings** from Understat and StatsBomb-derived player signals
3. **FIFA / World Football Elo as a Bayesian prior** for overall team strength

Before this becomes actionable, the comparison layer must devig market prices, apply minimum-volume filters, and require Pinnacle-relative edge as described in `DEVELOPMENT.md`.

## Output to the shared `results/` folder

Once consolidated, every run should write one CSV to `../results/compound-model/<YYYY-MM-DD>/predictions.csv` with the standard 8-column schema. See [`../results/README.md`](../results/README.md) for the exact contract.

## Files in this folder

```
compound-model/
├── README.md                    # this file
├── MODEL.md                     # standardized model card
└── docs/
    └── plans/
        └── 2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md
                                  # full implementation plan
```

The `src/`, `notebooks/`, `tests/`, etc. directories should appear only when they support the priority stack in `DEVELOPMENT.md`.

## Compare against other models

```bash
# Diff our predictions against another model on the same day
diff <(cut -d, -f2-5 ../results/compound-model/2026-05-15/predictions.csv | sort) \
     <(cut -d, -f2-5 ../results/<other-model>/2026-05-15/predictions.csv | sort)
```

Or in pandas:
```python
import pandas as pd
ours = pd.read_csv("../results/compound-model/2026-05-15/predictions.csv")
theirs = pd.read_csv("../results/<other-model>/2026-05-15/predictions.csv")
joined = ours.merge(theirs, on=["match_id","market_type","outcome"], suffixes=("_ours","_theirs"))
joined["disagreement"] = (joined["p_model_ours"] - joined["p_model_theirs"]).abs()
print(joined.sort_values("disagreement", ascending=False).head(20))
```
