---
status: aspirational
moved_from: docs/agents/synthesis-orchestrator.md
moved_on: 2026-05-15
---

# Synthesis: Orchestrator (aspirational)

> **Status — aspirational.** Implementation sibling of role 08; preserved alongside the parent spec at `2026-05-15-role-08-orchestration.md`.

## Mission

Run the project's weekly cadence. The Orchestrator is the **only role authorized to trigger** the cycle: pull markets, refresh acquisition snapshots, run modeling jobs, produce the comparison output, open a PR back to `main`. Everything else in the catalog is reactive; this role is the heartbeat.

The Orchestrator is implemented as a GitHub Actions workflow, not a daemon or a VM. Cost: $0/mo on a public repo with standard runners.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Cron trigger | `cron: '0 14 * * 0'` (Sunday 14:00 UTC) | Best-effort; delays of up to ~1h are normal for GitHub Actions cron |
| Manual trigger | `workflow_dispatch` with optional `date` input | For catch-up runs and smoke tests |
| All acquisition outputs | `data/derived/*.csv`, `data/derived/*.parquet` | Refreshed by `weekly_pull.py` step |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Workflow file | `.github/workflows/orchestrator-weekly.yml` | The canonical trigger |
| Pull request | branch `orchestrator/weekly-<date>`, base `main` | Title `chore(weekly): orchestrator snapshot <date>`, labels `orchestrator`, `weekly-snapshot` |
| Weekly summary | PR body | Names which steps ran, snapshots updated, gaps surfaced |

## Allowed write paths

- `.github/workflows/orchestrator-weekly.yml`
- The PR body and labels (via `peter-evans/create-pull-request@v6`)

**Forbidden:** direct push to `main`. The Orchestrator opens PRs; it does not merge them. Branch protection enforces this at the GitHub level too.

## Cadence

- `cron: '0 14 * * 0'` — Sunday 14:00 UTC
- `workflow_dispatch` — manual catch-up or smoke test, optional `date` input

Concurrency: `group: orchestrator-weekly`, `cancel-in-progress: false` — back-to-back runs queue rather than overlap.

## Guardrails

- Branch naming exception: `orchestrator/weekly-<date>` instead of `<your-name>/<description>`. Documented here so the [Review role](quality-review.md) does not flag it.
- The workflow runs deterministic Python — `weekly_pull.py`, `audit_player_coverage.py`, `validate_predictions.py`. **No LLM-driven steps**, which keeps this inside the [DEVELOPMENT.md deferred-list](../../DEVELOPMENT.md#current-priority-stack) constraint on "LLM/agent-driven scraping."
- Required repo settings: `Settings → Actions → General` → Workflow permissions = "Read and write" + "Allow GitHub Actions to create and approve pull requests" enabled. Without these, `peter-evans/create-pull-request` returns 403.
- Failed runs notify the repo admin via GitHub Actions default — no extra notification step needed.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Comparison/Edge](synthesis-comparison-edge.md) | New `results/comparisons/<date>/` | weekly |
| [Coverage Audit](quality-coverage-audit.md) | Audit script run as part of the workflow | weekly |
| [Validation/Backtest](quality-validation-backtest.md) | `validate_predictions.py --all` step | weekly |
| [Review](quality-review.md) | The opened PR | weekly |
| [Documentation/Learnings](synthesis-documentation-learnings.md) | Weekly summary in PR body | weekly |

## Escalation

- Stop and escalate if: the workflow run fails on `weekly_pull.py` or `validate_predictions.py` — the failed Action notifies the admin; do not silently swallow.
- Stop and escalate if: the PR-creation step returns 403 — repo settings are wrong; flip the toggles.
- Stop and escalate if: a weekly run produces a PR that conflicts with an open orchestrator PR (peter-evans/create-pull-request updates the existing branch by default; investigate before forcing).
- Stop and escalate if: the Sunday run misses for two consecutive weeks — switch to manual `workflow_dispatch` until the cron issue is resolved.

## Verification

- `.github/workflows/orchestrator-weekly.yml` exists and lints cleanly.
- One manual `workflow_dispatch` run completes successfully with `date: 2026-04-28` (smoke test).
- The resulting PR has labels `orchestrator` and `weekly-snapshot`.
- `Settings → Actions → General` toggles are enabled.
- After the first month of operation, the repo's Actions usage page shows $0 charged (public repo unlimited minutes).

## Status

**Workflow shipped in [PR #6](https://github.com/pol-i-tech/fulbol-mundial-26/pull/6).** First scheduled run: the next Sunday after merge. First manual run: as a smoke test immediately after the repo settings are toggled.
