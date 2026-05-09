# 04 · Market Normalization Agent

> Function-first agent: **devig & filter**. Specialized transform sibling of the Data Cleaning Agent — separated because the math is bookmaker-specific and dictates whether downstream edge calls are even valid.

## Mission

Convert raw bookmaker quotes into clean, devigged probabilities and apply liquidity rules so the Edge Agent can join models against a meaningful market. The Market Normalization Agent owns Power devig (1X2), Shin devig (outright / group winner), the Kalshi phantom-team filter, the KXWCGAME ticker parser, and the `min_volume` liquidity gate. If a probability that the Edge Agent uses came from a bookmaker, this agent put it there.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Kalshi raw | `data/raw/kalshi/<date>/*.json` | Includes phantom teams at 1–8% — must filter. |
| Polymarket raw | `data/raw/polymarket/<date>/*.json` | |
| The Odds API raw | `data/raw/oddsapi/<date>/*.json` | Pinnacle and Hard Rock quotes. |
| Fixture list | `data/derived/fixtures.csv` (or via `weekly_pull.py`) | Inner-join target for phantom filtering. |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Kalshi devigged | `data/derived/kalshi_snapshot_<YYYY-MM-DD>.csv` | `match_id, market_type, outcome, raw_p, devigged_p, volume, ticker, as_of` |
| Polymarket devigged | `data/derived/polymarket_snapshot_<YYYY-MM-DD>.csv` | same schema |
| Pinnacle devigged | `data/derived/pinnacle_snapshot_<YYYY-MM-DD>.csv` | same schema |

## Allowed write paths

- `data/derived/{kalshi,polymarket,pinnacle}_snapshot_<YYYY-MM-DD>.csv`
- `tools/normalize_kalshi.py`, `tools/normalize_polymarket.py`, `tools/normalize_pinnacle.py`
- The `normalize_*` functions inside `tools/weekly_pull.py`

Forbidden: model `predictions.csv`, `results/comparisons/**`, edge flags, Kelly stakes.

## Cadence

- **Daily via Orchestrator**, immediately after Data Engineering pulls market raws.

## Guardrails

- See [DEVELOPMENT.md — Market normalization](../../DEVELOPMENT.md#market-normalization) — Power for 1X2, Shin for outrights / group winners.
- See [DEVELOPMENT.md — Key Constraints](../../DEVELOPMENT.md#key-constraints) — KXWCGAME ticker regex, Kalshi phantom-team rule.
- All market prices stored as implied probability ∈ [0, 1].
- Raw quoted prices are informational only — a row is not actionable until devigging and `min_volume` filters have run.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Edge / Comparison | `{kalshi,polymarket,pinnacle}_snapshot_<date>.csv` | Daily |
| Backtest / Validation | Same | When validating actionable PnL backtests |

## Escalation

- Stop and escalate if: phantom filter would drop **>30%** of Kalshi rows on a market — likely a fixture-list staleness issue, not a phantom problem.
- Stop and escalate if: devigged probabilities sum outside [0.99, 1.01] for a `(match_id, market_type)`.
- Stop and escalate if: Kalshi outright/group-winner volume is zero across **all** markets — operator-priced and unactionable, but downstream still needs to know.
- Stop and escalate if: `min_volume` thresholds change without a documented evidence trail.

## Verification

- Each `*_snapshot_<date>.csv` exists with a `devigged_p` column populated for every row.
- Sum of mutually exclusive `devigged_p` per `(match_id, market_type)` ∈ [0.99, 1.01].
- No row has `devigged_p` outside [0, 1].
- Every row that the Edge Agent later flags actionable passes `min_volume`.
