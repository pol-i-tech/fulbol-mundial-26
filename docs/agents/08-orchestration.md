# 08 · Orchestration Agent

> Function-first agent: **the heartbeat**. The only role authorized to *trigger* the others. The legacy `synthesis-orchestrator.md` spec is its implementation.

## Mission

Run the daily cycle on a schedule and hand off between agents in the right order. The Orchestrator triggers Data Engineering, Cleaning, Market Normalization, Modeling, Validation, Coverage, and Edge inside a single GitHub Actions job, then opens a PR back to `main` with the resulting snapshot. Even cron-driven runs go through PR review — `main` is protected, and the Orchestrator does not bypass branch protection.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Workflow inputs | `.github/workflows/orchestrator-daily.yml` `inputs.date` | Optional date override. |
| Repo state | full checkout | Fresh clone per run. |
| Coverage worklist | `data/derived/player_coverage_report.csv` (previous cycle) | Drives manual-pull priorities surfaced in PR body. |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Daily snapshot PR | branch `orchestrator/daily-<YYYY-MM-DD>` → `main` | All `data/derived/*` and `results/*/<date>/` updates from the cycle |
| Run summary | PR body | One section per agent step with logs/links |

## Allowed write paths

- `.github/workflows/orchestrator-daily.yml`
- `tools/weekly_pull.py` (the orchestration entry point — name kept for git history)
- The daily snapshot branch (auto-created by `peter-evans/create-pull-request`)

Forbidden: pushing directly to `main`, editing model code, fixing data inline. If a step fails, open the PR with the failure surfaced and let humans decide.

## Cadence

- **Cron:** `0 9 * * *` — every day at 09:00 UTC.
- **Manual:** `workflow_dispatch` with optional `date` input.
- **For now we trigger manually.** The cron line is configured but operators will run via `workflow_dispatch` until the daily pipeline is observed stable for at least one week. Flip to fully automated by leaving the `schedule` block uncommented.

GitHub Actions cron is best-effort — delays of up to ~1h are normal. The job is concurrency-locked (`group: orchestrator-daily, cancel-in-progress: false`) so two runs cannot race.

## Guardrails

- See [DEVELOPMENT.md — Contribution Workflow](../../DEVELOPMENT.md#contribution-workflow) — `main` is protected, every PR needs one approving review.
- See [DEVELOPMENT.md — Running the Pipeline](../../DEVELOPMENT.md#running-the-pipeline) — `weekly_pull.py` is the entry point.
- Step order is non-negotiable: Data Engineering → Cleaning → Market Normalization → Modeling → Validation → Coverage → Edge.
- Timeout: 20 minutes. If a step exceeds, the run fails and a PR with logs is still opened so the failure is visible.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| All other agents | Triggers via workflow steps | Daily |
| Review (human) | PR `orchestrator/daily-<date>` | Daily |
| Documentation / Learnings | PR body + step logs | Daily |

## Escalation

- Stop and escalate if: any step fails — open the PR with the failure surfaced; do not retry inside the job.
- Stop and escalate if: PR creation fails (token / permission issue).
- Stop and escalate if: cron has skipped >2 consecutive scheduled days without a manual run filling the gap.
- Stop and escalate if: a daily snapshot PR sits unreviewed >72h — coverage report drifts and edge calls go stale.

## Verification

- A PR `orchestrator/daily-<YYYY-MM-DD>` is open within ~1h of 09:00 UTC (or immediately on `workflow_dispatch`).
- All seven step logs are attached to the PR body.
- The `validate-predictions` CI check is green on the PR before any human reviewer engages.
- Concurrency lock holds — no two simultaneous runs of the workflow.
