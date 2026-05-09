# Modeling: Compound-model

## Mission

Maintain the production wrapper that blends the three pillars of the project's predictive stack: time-decayed Dixon-Coles on international results, FIFA/World Football Elo as a Bayesian prior, and club-xG-aggregated lineup ratings from `squad_xg_ratings.parquet`. The compound-model is the *intended actionable output* for edge betting once devigging, liquidity filters, and Pinnacle comparison are wired into the comparison layer. See [`compound-model/README.md`](../../compound-model/README.md).

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Ensemble predictions | `results/ensemble-v2/<date>/predictions.csv` | Base prior |
| Squad xG ratings | `data/derived/squad_xg_ratings.parquet` | Player-level attack signal — **highest priority unwired feature** per [DEVELOPMENT.md](../../DEVELOPMENT.md#key-constraints) |
| Team attack ratings | `data/derived/team_attack_ratings.parquet` | Team-level aggregation |
| martj42 results | `data/raw/martj42/latest/results.csv` | For Dixon-Coles fit on 7.9k modern internationals |
| eloratings.net | `data/derived/elo_snapshot_<date>.csv` | Bayesian prior |
| Match importance weights | `WC=1.0, Euro/Copa=0.9, WCQ=0.7, Nations League=0.6, friendly=0.35` | See [DEVELOPMENT.md](../../DEVELOPMENT.md#match-importance-weights-recency-decay) |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Predictions | `results/compound-model/<YYYY-MM-DD>/predictions.csv` | [8-column schema](../../DEVELOPMENT.md#prediction-output-schema) |
| Tournament simulation | `results/wc2026-sim/probabilities.csv` | 10k Monte Carlo of 2026 bracket |
| Methodology code | `methodology/compound-model/compound.py` | TODO; consolidates `tools/build_2026_ratings.py` etc. |
| Model card | `compound-model/MODEL.md` | Already exists; update on changes |
| CHANGELOG | `methodology/compound-model/CHANGELOG.md` | Per [refinement-loop](refinement-loop.md) |

## Allowed write paths

- `methodology/compound-model/`
- `results/compound-model/`
- `results/wc2026-sim/`
- `compound-model/` (existing folder; for documentation and plan files)

## Cadence

`weekly` — Sunday cron via the Orchestrator, but **only after** the comparison-layer P0 gaps close (devigging + Pinnacle pull). Until then, snapshots are research-grade and not eligible for edge calculation.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails).
- Log-loss < 1.099. Target: beat or plausibly complement `ensemble-v2` on a held-out tournament.
- **`squad_xg_ratings.parquet` exists but is not yet wired in** — wiring it triggers [refinement-loop](refinement-loop.md), and the [Player Data Gap Plan guardrails](../plans/2026-05-06-player-data-gap-plan.md#required-guardrails) must all be satisfied first (missing-player fallback, freshness check, name overrides, backtest evidence).
- Tournament simulation only after match-level probabilities pass backtests — see [compound-model README phase plan](../../compound-model/README.md#status).

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Comparison/Edge](synthesis-comparison-edge.md) | `results/compound-model/<date>/predictions.csv` | weekly (when production-ready) |
| [Documentation/Learnings](synthesis-documentation-learnings.md) | Snapshot drift, simulation results | continuous |

## Escalation

- Stop and escalate if: a refinement attempt to wire in `squad_xg_ratings.parquet` worsens calibration on Euro2024 or Copa2024.
- Stop and escalate if: `tools/validate_predictions.py` fails on the compound output.
- Stop and escalate if: tournament simulation produces a final-winner distribution where the top team has > 35% win probability (suggests overconfidence or a fitting bug).
- Stop and escalate if: compound-model is asked to ship as actionable before market-normalization gaps close.

## Verification

- Output passes the validator.
- Snapshot exists for the date and matches the 8-column schema.
- WC2022 backtest log-loss ≤ 1.054 (ensemble baseline) before claiming improvement.
- ECE on a held-out tournament documented in `MODEL.md`.

## Status

**Plan + model card exist; production consolidation pending.** [`compound-model/README.md`](../../compound-model/README.md) phase plan: Phase 0 (guardrails) ongoing, Phase 1 (market correctness) is the gate, Phase 2 (player coverage) parallel, Phase 3 (consolidated model) is the goal of this role, Phase 4 (sim) deferred.
