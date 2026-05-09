# Synthesis: Comparison / Edge

## Mission

Join every model's predictions against devigged market prices, compute model-vs-market edge per the project's Golden Zone rule, and produce the actionable comparison artifacts. The Comparison role is the **only** path from "model output" to "actionable bet candidate." Everything upstream produces probabilities; this role decides which ones deserve a stake.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Model snapshots | `results/<model>/<YYYY-MM-DD>/predictions.csv` for every active model | Required |
| Market snapshots | `data/derived/kalshi_snapshot_<date>.csv`, `polymarket_snapshot_<date>.csv`, `pinnacle_snapshot_<date>.csv` | All three required for edge calc |
| Devig parameters | Power for 1X2, Shin for outrights — see [DEVELOPMENT.md](../../DEVELOPMENT.md#market-normalization) | Currently not yet wired into production |
| Volume thresholds | Per market type — TBD; see [data-gaps roadmap Markets](data-gaps-roadmap.md#markets) | Required before any "actionable" flag |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Comparison table | `results/comparisons/<YYYY-MM-DD>/comparison.csv` | All models + market prices side-by-side |
| Comparison narrative | `results/comparisons/<YYYY-MM-DD>/comparison.md` | Human-readable summary |
| Actionable list | `results/comparisons/<YYYY-MM-DD>/actionable.md` | Golden Zone + edge-threshold filter |
| Disagreement classification | Inline columns in `comparison.csv` | Per [WC2022 disagreement learning](../solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md) |

## Allowed write paths

- `results/comparisons/<date>/`
- `tools/weekly_pull.py` (the comparison-output section)

**Forbidden:** modifying any model's `predictions.csv`. The Comparison role joins; it does not edit.

## Cadence

`weekly` — runs as the final step of the Orchestrator's Sunday cycle, after every model has produced a same-date snapshot.

## Guardrails

- See [DEVELOPMENT.md — Betting rule](../../DEVELOPMENT.md#betting-rule):
  - **Golden Zone:** all 3 base models (Elo, Form, Poisson) agree on the same favourite
  - **Edge threshold:** model_p > devigged_market_p by ≥ 3% AND > Pinnacle by ≥ 1.5%
  - **Kelly sizing:** half-Kelly, capped at 2% bankroll
  - **Skip:** 3-way model splits
- See [WC2022 disagreement learning](../solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md) for the disagreement taxonomy.
- **Do not flag actionable** until devigging is implemented — see [data-gaps roadmap](data-gaps-roadmap.md#markets).
- Filter Kalshi outright/group markets on `min_volume` before flagging edge.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Orchestrator](synthesis-orchestrator.md) | `comparison.csv`, `actionable.md` for weekly summary | weekly |
| [Documentation/Learnings](synthesis-documentation-learnings.md) | Surprising edges or disagreement patterns | continuous |

## Escalation

- Stop and escalate if: any model snapshot is missing for the target date.
- Stop and escalate if: market snapshot prices are > 7 days stale.
- Stop and escalate if: devigging is not yet implemented but a contributor PRs an "actionable" flag.
- Stop and escalate if: a 3-way model split appears in `actionable.md` (must be skipped, not flagged).

## Verification

- `comparison.csv` has one row per (match_id, market_type, outcome) with columns for every active model and every market source.
- Disagreement classification is computed and joinable.
- `actionable.md` includes only Golden-Zone bets that clear the Kalshi/Pinnacle edge thresholds.
- Filter audit: no row in `actionable.md` has `min_volume = 0` or a 3-way model split.

## Status

**Snapshot-producing today** (`weekly_pull.py` produces `comparison.csv`). Devigging, Pinnacle integration, and `actionable.md` filter logic are open work — see [data-gaps roadmap Markets](data-gaps-roadmap.md#markets).
