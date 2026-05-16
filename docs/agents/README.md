# Agent Catalog

This directory is the canonical map of who does what on `fulbol-mundial-26`. Every contributor — human or AI — picks a **role** from this catalog before touching the repo. The role spec tells you what you can read, what you can write, what you must verify, and when to escalate.

Roles are *responsibilities*, not people. One person or one agent may fill several roles. A role can be held by a human one week and a Claude/Cursor/Codex/Gemini agent the next. The catalog stays the same.

This catalog operationalizes the rules in [`../../DEVELOPMENT.md`](../../DEVELOPMENT.md). When a role spec and `DEVELOPMENT.md` disagree, **`DEVELOPMENT.md` wins** — open a PR to fix the role spec.

## The 6 functional roles

The active catalog. Pick one of these. Each spec is tight: what it reads, what it writes, what it must not do, when it runs, and how it knows it's done.

| # | Role | Single job |
|---|---|---|
| 01 | [Data Engineering](01-data-engineering.md) | Fetch external data into `data/raw/<source>/<date>/`. Nothing else. |
| 02 | [Data Coverage](02-data-coverage.md) | Read-only. Detect gaps + staleness. Write `player_coverage_report.csv`. |
| 03 | [Data Cleaning & Feature Engineering](03-data-cleaning.md) | `data/raw/**` → `data/derived/*.parquet`. The only role that owns transformations. |
| 05 | [Modeling / Data Science](05-modeling.md) | Fit the WC2026 predictor against the curated layer. Write `predictions.csv`. |
| 06 | [Backtest / Validation](06-validation.md) | Schema gate per PR + held-out backtest per methodology change. The only promotion gate. |
| 08 | [Orchestration](08-orchestration.md) | Daily 09:00 UTC cron. Triggers 01 → 06 in order, opens a PR. |

> **Note:** Roles 04 (Market Normalization) and 07 (Edge / Comparison) have been removed from the catalog. The project's scope is producing match probabilities — devig, market comparison, and actionable-edge work are out of scope.

## Org chart

```mermaid
flowchart LR
    O[08 · Orchestration<br/>daily 09:00 UTC]
    DE[01 · Data Engineering<br/>fetch raw]
    DC[02 · Data Coverage<br/>find gaps]
    CL[03 · Cleaning + FE<br/>raw → derived]
    MD[05 · Modeling<br/>probabilities]
    VA[06 · Validation<br/>backtest gate]

    O --> DE --> CL --> MD --> VA
    O --> DC
    DC -.gap signal.-> DE
    VA -.verdict.-> MD
```

## Cadence at a glance

| Role | Schedule | Where |
|---|---|---|
| 01 Data Engineering | Daily for cron sources (martj42, Markets); on-demand for episodic sources | `tools/pull_*.py` |
| 02 Data Coverage | Daily inside Orchestrator + per-PR on `data/derived/` changes | `tools/audit_player_coverage.py` |
| 03 Cleaning + FE | Daily, after 01 | `tools/aggregate_*.py`, `tools/build_*.py` |
| 05 Modeling | Daily, after 03 | `methodology/<model>/`, `results/<model>/<date>/` |
| 06 Validation | Per-PR (schema) + per-refinement (backtest) | `.github/workflows/validate-predictions.yml`, `wc2022_xg_backtest.py` |
| 08 Orchestration | `cron: "0 9 * * *"` (daily 09:00 UTC) + `workflow_dispatch`. **Manual-only for now.** | `.github/workflows/orchestrator-daily.yml` |

**Net: one scheduled cron tick per day at 09:00 UTC drives 01 → 06 in sequence. Validation also fires per-PR. Everything else is reactive.**

## Implementation specs (per source / per model)

The 8 functional roles above are the contract. Each one has concrete *implementations* — one per data source, per model, per quality gate. Browse these when picking up a specific deliverable; the parent role spec dictates the rules.

### Implementations of 01 · Data Engineering

- [International Results (martj42)](acquisition-international-results.md)
- [StatsBomb xG](acquisition-statsbomb.md)
- [Understat club xG](acquisition-understat.md)
- [WC2026 squads](acquisition-wc2026-squads.md)
- [National lineups (FIFA / UEFA / federation)](acquisition-national-lineups.md)
- [Elite-club form (UCL / UEL)](acquisition-elite-club-form.md)

### Implementations of 05 · Modeling

- [Elo baseline](modeling-elo-baseline.md)
- [Form-last-10](modeling-form-last-10.md)
- [Poisson-goals](modeling-poisson-goals.md)
- [xG-Poisson](modeling-poisson-xg.md)
- [Ensemble](modeling-ensemble.md)
- [Compound-model](modeling-compound-model.md)

### Implementations of 02 · Coverage and 06 · Validation

- [Coverage Audit](quality-coverage-audit.md)
- [Validation / Backtest](quality-validation-backtest.md)
- [Review](quality-review.md)

### Implementations of 08 · Orchestration

- [Documentation / Learnings](synthesis-documentation-learnings.md)
- [Orchestrator](synthesis-orchestrator.md)

### Storytelling / Public output

- [Storytelling Report Writer](storytelling-report-writer.md) — produces the < 2-page Graphene-rendered narrative report (`graphene-app-world-cup/wc2026_tournament_report.md`) summarizing the predictor's view of the tournament. Tone: funny, smart, structurally humble.

## Cross-cutting documents

- [Role template](_role-template.md) — copy this when adding a new role.
- [Data gaps roadmap](data-gaps-roadmap.md) — what 01 should chase next.
- [Refinement loop](refinement-loop.md) — how 05 changes parameters without violating no-post-hoc-fitting.

## How a role gets added

1. Copy [`_role-template.md`](_role-template.md) to a new file under this directory.
2. Fill in every section. No empty sections — if something doesn't apply, say so explicitly.
3. Add the role to the "8 functional roles" table above (or as an implementation of an existing role).
4. Update [`../../AGENTS.md`](../../AGENTS.md) and [`../../CLAUDE.md`](../../CLAUDE.md) so the new role is reachable from the entry point.
5. Open a PR. The Validation Agent enforces schema; the human reviewer checks scope.
