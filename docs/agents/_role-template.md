# <Role Name>

> **Template.** Copy this file to `docs/agents/<role-name>.md` and fill every section. Delete this blockquote when done. Empty sections are not allowed — if a field doesn't apply, write "N/A — <reason>".

## Mission

One paragraph. The durable purpose of the role. What problem does this role solve for the project?

## Inputs

Files, sources, or upstream artifacts this role consumes. Use repo-relative paths. For external sources, include the URL and any rate-limit / policy notes.

| Input | Path or URL | Notes |
|---|---|---|
|  |  |  |

## Outputs

Files this role writes. Use repo-relative paths. For each, name the schema or link to it.

| Output | Path | Schema |
|---|---|---|
|  |  |  |

## Allowed write paths

Explicit list of paths the role is allowed to create or modify. **Anything not listed here is forbidden.** Reviewers reject PRs that write outside this list.

- `path/to/allowed/dir/`
- `path/to/specific/file`

## Cadence

When the role runs. Pick one or describe:

- `weekly` — every Sunday via the Orchestrator
- `on-demand` — when triggered by an upstream signal
- `continuous` — whenever new evidence arrives
- `per-PR` — runs against every pull request

## Guardrails

Which `DEVELOPMENT.md` rules are load-bearing for this role. Cite by section name with a relative link, do not duplicate the rule text.

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails)
- See [DEVELOPMENT.md — Subjectivity and bias policy](../../DEVELOPMENT.md#subjectivity-and-bias-policy)

## Hand-offs

Which roles consume this role's output, and via what artifact.

| Downstream role | Artifact | Frequency |
|---|---|---|
|  |  |  |

## Escalation

When to stop and ask a human lead. List concrete stop-conditions, not generic "if something looks wrong."

- Stop and escalate if: <specific failure mode>
- Stop and escalate if: <specific failure mode>

## Verification

How the role knows it is done. Specific, observable outcomes.

- <Outcome>
- <Outcome>
