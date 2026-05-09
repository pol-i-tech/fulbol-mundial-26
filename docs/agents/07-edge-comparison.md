# 07 · Edge / Comparison Agent

> Function-first agent: **model vs. market**. The only role allowed to label a row *actionable*. The legacy `synthesis-comparison-edge.md` spec is its concrete implementation.

## Mission

Join every model's predictions against devigged market prices and emit the bet list. The Edge Agent runs after Modeling and Market Normalization are both green for the same date. It applies the Golden Zone rule (all 3 base models agree on the favourite), the edge thresholds (≥3% vs devigged market AND ≥1.5% vs Pinnacle), and half-Kelly sizing capped at 2% of bankroll. Anything that ends up in `actionable.md` came through this agent's filter — nothing else is allowed to write that file.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Per-model predictions | `results/<model>/<YYYY-MM-DD>/predictions.csv` | All models with same `as_of_date`. |
| Devigged Kalshi snapshot | `data/derived/kalshi_snapshot_<YYYY-MM-DD>.csv` | From Market Normalization. |
| Devigged Polymarket snapshot | `data/derived/polymarket_snapshot_<YYYY-MM-DD>.csv` | From Market Normalization. |
| Devigged Pinnacle snapshot | `data/derived/pinnacle_snapshot_<YYYY-MM-DD>.csv` | Required for the secondary edge gate. |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Full join | `results/comparisons/<YYYY-MM-DD>/comparison.csv` | every model + every market per row |
| Narrative summary | `results/comparisons/<YYYY-MM-DD>/comparison.md` | human-readable report |
| Actionable list | `results/comparisons/<YYYY-MM-DD>/actionable.md` | Golden-Zone passes only, with Kelly stake |

## Allowed write paths

- `results/comparisons/<YYYY-MM-DD>/**`
- `tools/compare_models.py`, the comparison logic in `tools/weekly_pull.py`

Forbidden: editing any model's `predictions.csv`, changing devig methods, modifying market snapshots, placing bets.

## Cadence

- **Daily via Orchestrator**, last step of the cycle, after Modeling + Market Normalization + Validation are all green.

## Guardrails

- See [DEVELOPMENT.md — Betting rule](../../DEVELOPMENT.md#betting-rule) — Golden Zone, edge thresholds, half-Kelly cap.
- See [DEVELOPMENT.md — Architecture, Market normalization](../../DEVELOPMENT.md#market-normalization) — actionable requires devig + `min_volume`.
- Skip 3-way model splits — when base models disagree, no actionable row.
- Edge detection lives only here; models' `notes` fields must not mention markets.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Documentation / Learnings | `comparison.md`, `actionable.md` | Daily |
| Orchestrator (PR body) | Top-line edge count + Golden Zone count | Daily |

## Escalation

- Stop and escalate if: any actionable row fails `min_volume`.
- Stop and escalate if: Pinnacle snapshot is missing but Kalshi/Polymarket are present — gate (b) cannot fire, so no actionable rows are valid.
- Stop and escalate if: a model is missing for the snapshot date — comparison would be skewed.
- Stop and escalate if: total Golden Zone bets in a single cycle exceeds 10% of bankroll cumulatively (sanity cap on stake concentration).

## Verification

- `comparison.csv` exists with one row per `(match_id, market_type, outcome)` joined across all models and markets.
- Every row in `actionable.md` independently passes the Golden Zone rule, both edge gates, and `min_volume`.
- Half-Kelly stakes are capped at 2% bankroll per row and ≤10% bankroll across the cycle.
- `actionable.md` is empty (not missing) when no row qualifies — the file always exists.
