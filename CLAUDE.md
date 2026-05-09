# CLAUDE.md

Entry point for Claude Code (and any AI agent) joining `fulbol-mundial-26`. Identical in substance to [`AGENTS.md`](./AGENTS.md) — kept aligned by convention.

## Where you are

A multi-contributor 2026 World Cup prediction workbench. Models produce probabilities; the comparison framework joins them against devigged market prices to find positive-edge bets. See [`README.md`](./README.md) and [`DEVELOPMENT.md`](./DEVELOPMENT.md).

## Pick a role

The full catalog and org chart is at [`docs/agents/README.md`](./docs/agents/README.md). 19 named roles across four groups:

### Data Acquisition

- [International results (martj42)](./docs/agents/acquisition-international-results.md)
- [StatsBomb xG](./docs/agents/acquisition-statsbomb.md)
- [Understat club xG](./docs/agents/acquisition-understat.md)
- [WC2026 squads](./docs/agents/acquisition-wc2026-squads.md)
- [National lineups (FIFA / UEFA / federation)](./docs/agents/acquisition-national-lineups.md)
- [Elite-club form (UCL / UEL)](./docs/agents/acquisition-elite-club-form.md)
- [Markets (Kalshi / Polymarket / Pinnacle)](./docs/agents/acquisition-markets.md)

### Modeling

- [Elo baseline](./docs/agents/modeling-elo-baseline.md)
- [Form-last-10](./docs/agents/modeling-form-last-10.md)
- [Poisson-goals](./docs/agents/modeling-poisson-goals.md)
- [xG-Poisson](./docs/agents/modeling-poisson-xg.md)
- [Ensemble](./docs/agents/modeling-ensemble.md)
- [Compound-model](./docs/agents/modeling-compound-model.md)

### Quality

- [Coverage Audit](./docs/agents/quality-coverage-audit.md)
- [Validation / Backtest](./docs/agents/quality-validation-backtest.md)
- [Review](./docs/agents/quality-review.md)

### Synthesis

- [Comparison / Edge](./docs/agents/synthesis-comparison-edge.md)
- [Documentation / Learnings](./docs/agents/synthesis-documentation-learnings.md)
- [Orchestrator](./docs/agents/synthesis-orchestrator.md) — weekly cadence; the only role authorized to *trigger* the cycle

## Cross-cutting

- [Role template](./docs/agents/_role-template.md) — copy when adding a new role
- [Data gaps roadmap](./docs/agents/data-gaps-roadmap.md) — what acquisition roles should chase next
- [Refinement loop](./docs/agents/refinement-loop.md) — how modeling roles change parameters without violating the no-post-hoc-fitting rule

## Where work happens

- Every contribution goes through a PR — `main` is protected. See [`DEVELOPMENT.md` — Contribution Workflow](./DEVELOPMENT.md#contribution-workflow).
- Branch naming: `<your-name>/<description>`, except the [Orchestrator role](./docs/agents/synthesis-orchestrator.md) which uses `orchestrator/weekly-<date>`.
- Every PR requires one approving review before merge.
- The four contributor tracks (Model / Data / Analysis / Docs) in `DEVELOPMENT.md` describe *what surface to land on*; the role catalog above describes *what responsibility you take on*.

## Priority stack

The canonical priority order is in [`DEVELOPMENT.md` — Current Priority Stack](./DEVELOPMENT.md#current-priority-stack). Do not freelance against it.

1. Guardrails and validation
2. Player-data coverage
3. Market normalization
4. Model consolidation
5. Then advanced features

## Conflict resolution

If a role spec and `DEVELOPMENT.md` disagree, **`DEVELOPMENT.md` wins** — open a PR to fix the role spec.
