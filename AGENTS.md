# AGENTS.md

Entry point for any contributor — human or AI — joining `fulbol-mundial-26`.

## Where you are

A 2026 World Cup prediction workbench. The repo builds a single model — `wc2026-predictor` — that reads the curated DuckDB layer and emits probabilities for every WC2026 match. See [`README.md`](./README.md) and [`DEVELOPMENT.md`](./DEVELOPMENT.md).

## Pick a role

The 6 functional roles below are the active catalog. Pick one. Each spec is tight: what it reads, what it writes, what it must not do, when it runs, and how it knows it's done.

| # | Role | Single job |
|---|---|---|
| 01 | [Data Engineering](./docs/agents/01-data-engineering.md) | Fetch external data into `data/raw/<source>/<date>/`. Nothing else. |
| 02 | [Data Coverage](./docs/agents/02-data-coverage.md) | Read-only. Detect gaps + staleness. Write `player_coverage_report.csv`. |
| 03 | [Data Cleaning & Feature Engineering](./docs/agents/03-data-cleaning.md) | `data/raw/**` → `data/derived/*.parquet`. The only role that owns transformations. |
| 05 | [Modeling / Data Science](./docs/agents/05-modeling.md) | Fit the WC2026 predictor against the curated layer. Write `predictions.csv`. |
| 06 | [Backtest / Validation](./docs/agents/06-validation.md) | Schema gate per PR + held-out backtest per methodology change. The only promotion gate. |
| 08 | [Orchestration](./docs/agents/08-orchestration.md) | Daily 09:00 UTC cron. Triggers 01 → 06, opens a PR. |

> Roles 04 (Market Normalization) and 07 (Edge / Comparison) are out of scope. The project produces match probabilities; devig and market-edge work do not live here.

The full org chart, cadence table, and per-source / per-model implementation specs are in [`docs/agents/README.md`](./docs/agents/README.md).

## Cross-cutting

- [Role template](./docs/agents/_role-template.md) — copy when adding a new role
- [Data gaps roadmap](./docs/agents/data-gaps-roadmap.md) — what 01 should chase next
- [Refinement loop](./docs/agents/refinement-loop.md) — how 05 changes parameters without violating the no-post-hoc-fitting rule
- [Documented solutions](./docs/solutions/) — best practices, bug fixes, and workflow learnings indexed by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or debugging in documented areas.

## Where work happens

- Every contribution goes through a PR — `main` is protected. See [`DEVELOPMENT.md` — Contribution Workflow](./DEVELOPMENT.md#contribution-workflow).
- Branch naming: `<your-name>/<description>`, except [Orchestration](./docs/agents/08-orchestration.md) which uses `orchestrator/daily-<date>`.
- Every PR requires one approving review before merge.
- The four contributor tracks (Model / Data / Analysis / Docs) in `DEVELOPMENT.md` describe *what surface to land on*; the role catalog above describes *what responsibility you take on*.

## Priority stack

The canonical priority order is in [`DEVELOPMENT.md` — Current Priority Stack](./DEVELOPMENT.md#current-priority-stack). Do not freelance against it.

1. Guardrails and validation
2. Player-data coverage
3. Model consolidation
4. Then advanced features

## Conflict resolution

If a role spec and `DEVELOPMENT.md` disagree, **`DEVELOPMENT.md` wins** — open a PR to fix the role spec.
