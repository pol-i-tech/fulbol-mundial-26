# 05 · Modeling / Data Science Agent

> Function-first agent: **probabilities**. Reads `curated.*` from `data/wc2026.duckdb`, fits the WC2026 predictor, writes one `predictions.csv` per snapshot. Stateless with respect to markets — never sees Kalshi, Polymarket, or Pinnacle.

*Current as of 2026-05-15.*

## Mission

Produce calibrated probability estimates for every WC2026 match (1X2, outright, group winner, advance, totals, BTTS). The Modeling Agent owns **one model** — `wc2026-predictor` — and ships exactly one `predictions.csv` per snapshot date. The contract is the canonical 8-column schema documented in [`db/SCHEMA.md`](../../db/SCHEMA.md) and [`DEVELOPMENT.md`](../../DEVELOPMENT.md#prediction-output-schema). Alternate models from future contributors land under their own `methodology/<model>/` and `results/<model>/` subtrees against the same contract — but only one model is canonical at any one time.

## Inputs

The model reads **only** from the curated layer in `data/wc2026.duckdb`. No raw parquet reads, no ad-hoc CSV joins.

| Input | Path | Notes |
|---|---|---|
| Curated DuckDB | `data/wc2026.duckdb` (table `curated.*`) | Canonical input — built by `tools/build_duckdb.py` from `data/derived/*.parquet` and `db/masters/*.csv`. |
| Schema reference | [`db/SCHEMA.md`](../../db/SCHEMA.md) | Quick Reference at top of file; per-table column docs below. |
| Example queries | [`db/queries/examples/`](../../db/queries/examples/) | Canonical read-patterns for team features, form, xG/xGA, recent results. |

If a needed feature is not in `curated.*`, do not bypass it — open a PR against the curated layer first (role 03 territory), then consume from curated.

## Outputs

| Output | Path | Schema |
|---|---|---|
| Snapshot predictions | `results/<model-name>/<YYYY-MM-DD>/predictions.csv` | Canonical 8-column schema (see `db/SCHEMA.md` and `DEVELOPMENT.md`). |
| Methodology | `methodology/<model-name>/` | `README.md`, model code, `requirements.txt`. |
| Model card | `results/<model-name>/MODEL.md` | Documents subjective adjustments + limitations. |

Today the single canonical model is `wc2026-predictor` (currently lives under `methodology/curated-poisson-luck/` pending the Phase C rename).

## Allowed write paths

- `methodology/<model-name>/**`
- `results/<model-name>/<YYYY-MM-DD>/predictions.csv`
- `results/<model-name>/MODEL.md`

Forbidden: `data/raw/**`, `data/derived/**`, `db/curated/**` (the curated layer is owned by role 03), any other model's directory.

## Cadence

- **On any methodology change** — must come paired with a Backtest Agent verdict before merge.
- **On any curated-layer change** that materially shifts inputs — re-snapshot.

There is no daily cron today; `tools/weekly_pull.py` and the predictor are run manually. The orchestration spec for an automated cadence lives in [`docs/ideation/2026-05-15-role-08-orchestration.md`](../ideation/2026-05-15-role-08-orchestration.md).

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails) — required artifacts, reproducibility standard.
- See [DEVELOPMENT.md — Subjectivity and bias policy](../../DEVELOPMENT.md#subjectivity-and-bias-policy) — every manual parameter must live in `MODEL.md` under "Subjective adjustments".
- See [DEVELOPMENT.md — Statistical validation bar](../../DEVELOPMENT.md#statistical-validation-bar) — log-loss < 1.099, walk-forward only.
- See [`refinement-loop.md`](./refinement-loop.md) — how to change parameters without violating no-post-hoc-fitting.
- **No hardcoded modeling weights.** Tier weights, importance dicts, project-wide priors live in `db/masters/*.csv` → `curated.dim_*`, never as `CASE` literals in model code.
- Probabilities for mutually exclusive outcomes sum to [0.99, 1.01] per `(match_id, market_type)`.
- 3-letter FIFA codes throughout — never free-form country names.
- `notes` describes model reasoning only; **never** market comparisons or edge flags.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Backtest / Validation | `predictions.csv` for the snapshot date | Per snapshot, per PR |
| Documentation / Learnings | `MODEL.md`, refinement notes | On methodology change |

## Escalation

- Stop and escalate if: a probability sum falls outside [0.99, 1.01].
- Stop and escalate if: any `p_model` is outside [0, 1].
- Stop and escalate if: a manual parameter changed between snapshots without a Backtest Agent verdict.
- Stop and escalate if: log-loss on the most recent held-out tournament falls below the prior champion's number.
- Stop and escalate if: a needed feature requires reading outside `curated.*` — pause and open a curated-layer PR first.

## Verification

- `tools/validate_predictions.py results/<model>/<YYYY-MM-DD>/predictions.csv` exits 0.
- The `methodology/<model>/` folder is runnable from a clean clone and regenerates the snapshot deterministically.
- `MODEL.md`'s "Subjective adjustments" section is non-empty and matches the actual code.
- Backtest Agent's report exists for every methodology change.

## Contributing an alternate model

Future contributors who want to ship a competing model:

1. Copy `methodology/_template/` to `methodology/<your-model>/`.
2. Read from `curated.*` only — same contract as the canonical model.
3. Write `predictions.csv` matching `db/SCHEMA.md` and `DEVELOPMENT.md`'s 8-column schema.
4. Provide `MODEL.md` per the subjectivity policy.
5. Open a PR. Validation Agent enforces the schema gate; the Backtest Agent runs the walk-forward check.

The catalog stays a single role — there is one Modeling job — but more than one model can live in the tree as long as each one meets the contract.
