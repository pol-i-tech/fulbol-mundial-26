# fulbol-mundial-26

**[→ View the live prediction report](https://lnoguera171.github.io/fulbol-mundial-26/)** — methodology, 48-team probabilities, predicted bracket.

A **multi-contributor** workbench for predicting the 2026 FIFA World Cup. The goal is simple: every participant brings their own modeling approach, drops their estimations into a common results folder, and the group compares them against prediction-market prices (Kalshi, Polymarket, Hard Rock Bet) to find positive-edge betting opportunities.

The repo is a tournament between approaches. We don't care whether a model is hand-built in a spreadsheet, a Bayesian hierarchy in Stan, or a quick gut-feel tier list — if it produces probabilities and writes them in the standard format, the comparison framework treats them all equally.

## Current Status

As of 2026-05-06, this repo is no longer just a plan. It contains:

- Shared raw and derived data snapshots under `data/`.
- 2026-04-28 prediction snapshots for `elo-baseline`, `form-last-10`, `poisson-goals`, and `ensemble-e3`.
- A WC 2022 walk-forward backtest for the xG-patched ensemble.
- A weekly market pull / comparison script in `tools/weekly_pull.py`.
- A prediction validator in `tools/validate_predictions.py`.

The project is still pre-tournament and research-grade. Treat every betting output as analysis until it passes the model guardrails in `DEVELOPMENT.md`.

## Structure

```
fulbol-mundial-26/
├── README.md                       # this file — project overview
├── compound-model/                 # project-level model plan and model card
│   ├── README.md                   # what this model does
│   ├── MODEL.md                    # standardized model card
│   └── docs/plans/                 # full implementation plan
├── methodology/                    # reproducible model code
│   └── _template/
├── tools/                          # data pulls, validation, comparison
├── data/                           # committed seed snapshots and derived data
└── results/                        # SHARED output zone
    ├── README.md                   # the schema everyone writes to
    └── _template/                  # blank predictions.csv template
```

## How it works

1. **You build a model** — any methodology. Statistical, market-derived, hand-curated, hybrid.
2. **You produce estimations** — probabilities for the matches/markets you want to call.
3. **You write a CSV** to `results/<your-model-name>/<YYYY-MM-DD>/predictions.csv` following the schema in [`results/README.md`](results/README.md).
4. **You write a `MODEL.md`** in `results/<your-model-name>/` describing the approach, author, methodology, validation, limitations, and subjective adjustments.
5. **The group compares** estimations side-by-side against prediction-market prices to surface where models agree, where they diverge, and where there's an exploitable edge.

## Contributing models

To add your model:

```bash
cp -r methodology/_template methodology/<your-model-name>
mkdir -p results/<your-model-name>
cp results/_template/MODEL.md results/<your-model-name>/MODEL.md
```

Then edit `methodology/<your-model-name>/README.md`, fill in `results/<your-model-name>/MODEL.md`, and write snapshots to `results/<your-model-name>/<date>/predictions.csv`. See [`results/README.md`](results/README.md) for the exact CSV schema.

## Models currently in the repo

| Model | Folder | Approach | Status |
|---|---|---|---|
| elo-baseline | `results/elo-baseline/` | World Football Elo 1X2 baseline plus placeholder outright softmax | Snapshot exists for 2026-04-28 |
| form-last-10 | `results/form-last-10/` | Recent-results form signal | Snapshot exists for 2026-04-28 |
| poisson-goals | `results/poisson-goals/` | Time-decayed goals Poisson signal | Snapshot exists for 2026-04-28 |
| ensemble-e3 | `results/ensemble-e3/` | Elo + goals-Poisson + Form blend | Snapshot exists for 2026-04-28; WC2022 backtest output exists |
| ensemble-v2 | `results/ensemble-v2/` | Equal-weight Elo + Form + xG-Poisson backtest | WC2022 backtest output exists |
| compound-model | [`compound-model/`](compound-model/) | Planned production wrapper around the above signals plus player xG ratings and tournament simulation | Model card and plan exist; implementation needs consolidation |

Add your row when you join.

## What everyone writes to `results/`

The shared schema is the contract. One CSV per model per day with these columns:

| Column | Example |
|---|---|
| `as_of_date` | 2026-04-28 |
| `match_id` | `WC26-MEX-RSA-2026-06-11` (or `OUTRIGHT-WC2026` for futures) |
| `market_type` | `match_1x2`, `outright_winner`, `group_winner`, `team_advances` |
| `outcome` | `home`, `draw`, `away`, or `<TEAM_CODE>` for outrights |
| `p_model` | 0.62 |
| `confidence` | `high`, `medium`, `low` (or numeric 0–1) |
| `model_version` | `v1.0` or git sha |
| `notes` | free-text optional |

Full details in [`results/README.md`](results/README.md). Validate date snapshots before opening a PR:

```bash
python3 tools/validate_predictions.py --all
```

## Why this format

- **Spreadsheet-friendly.** Anyone can open a CSV in Excel/Numbers, fill rows by hand, and contribute without writing code.
- **Diff-friendly.** Daily snapshots in dated folders make it trivial to track how a model's view evolved (and to spot last-minute changes that suggest information asymmetry).
- **Comparison-friendly.** Every model writing the same columns means a one-liner can join them all and produce the side-by-side table.

## Cost & infrastructure

Free for any contributor. The compound-model has its own credentials section ([`compound-model/README.md`](compound-model/README.md#cost-and-credentials)) — TL;DR $0/month on free API tiers, $30 once for backtest historical odds. Other models may have zero infra cost (e.g. a hand-curated tier list).

## License & ground rules

- Each contributor owns their model folder and their entries in `results/`.
- Do not modify another contributor's `results/<their-model>/...` files.
- Write to your own folder, on your own cadence.
- The bet ledger is private — each participant logs their own bets locally in `bets/ledger.csv` (gitignored).

## Scope Control

The project is intentionally narrow:

- Build reproducible probability snapshots.
- Compare those snapshots to market prices.
- Document model limitations before using probabilities for staking decisions.

Avoid new dashboards, scraping experiments, or model rewrites unless they improve one of those three goals. Current high-priority work is listed in `DEVELOPMENT.md`.
