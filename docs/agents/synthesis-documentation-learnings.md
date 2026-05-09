# Synthesis: Documentation / Learnings

## Mission

Keep the project's institutional memory fresh. Every notable finding — a model failure mode, a backtest insight, a data-source decision, a betting outcome — gets a learning document under `docs/solutions/best-practices/`. This role also keeps `DEVELOPMENT.md`, `AGENTS.md`, `CLAUDE.md`, and the agent catalog in sync. Documentation is not a janitorial role; it is the layer that prevents the project from re-learning the same lesson twice.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Weekly comparison output | `results/comparisons/<date>/` | Surfaces patterns worth a learning |
| PR descriptions and reviews | GitHub | Any "we learned X" worth elevating |
| Backtest results | `results/comparisons/wc2022-backtest/` | Source of model-roles insights |
| User feedback / postmortems | Ad-hoc | Triggered by surprising results |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Learning doc | `docs/solutions/best-practices/<topic>-<date>.md` | Per existing pattern (frontmatter + Context + Guidance + When to apply + Examples) |
| Doc updates | `DEVELOPMENT.md`, `AGENTS.md`, `CLAUDE.md` | When a learning produces a new rule |
| Catalog updates | `docs/agents/<role>.md` | When a learning changes a role's contract |
| Trend log | `docs/solutions/trends/<topic>-trend.md` (if needed) | Cross-week or cross-tournament patterns |

## Allowed write paths

- `docs/solutions/`
- `DEVELOPMENT.md`, `AGENTS.md`, `CLAUDE.md` (with care — these are canonical)
- `docs/agents/` (existing role specs only when a learning changes a contract)

**Forbidden:** modifying model code, acquisition scripts, or `results/<model>/<date>/` snapshots.

## Cadence

`continuous` — but at minimum once per weekly cycle (a brief learning summarizing the week's surprises) and once per merged PR that changes a model's methodology (the learning explaining what was learned).

## Guardrails

- Existing learnings format ([model-roles](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md), [WC2022 disagreement](../solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md)) is the canonical pattern. Do not invent a new format.
- A learning that produces a new rule must propose the `DEVELOPMENT.md` edit in the same PR — not a separate "I'll do it later."
- A learning that changes a role's contract must update the role spec in the same PR.
- Don't write learnings about ephemeral details (specific PR numbers, transient bugs). Write what would help a contributor 6 months from now.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Modeling roles | Learning that motivates a [refinement](refinement-loop.md) | continuous |
| [Coverage Audit](quality-coverage-audit.md) | Priority signal when a learning surfaces a new gap | continuous |
| All roles | Updated `DEVELOPMENT.md` / role specs | per learning |

## Escalation

- Stop and escalate if: a learning would change `DEVELOPMENT.md` in a way that affects existing model snapshots' interpretation (could invalidate prior bet outcomes).
- Stop and escalate if: a finding contradicts an existing learning — reconcile both in one PR, do not let two opposing learnings co-exist.
- Stop and escalate if: a learning is being written to justify a post-hoc parameter change (the [refinement-loop](refinement-loop.md) protocol takes precedence).

## Verification

- New learning has the correct frontmatter (title, date, category, module, problem_type, component, severity, applies_when, tags).
- Learning is placed under `docs/solutions/best-practices/` with the date suffix.
- Cross-references from `DEVELOPMENT.md` or role specs to the learning are added.
- Existing learnings cited by a new one are still accessible (no broken links).
