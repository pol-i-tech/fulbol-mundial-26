# Quality: Review

## Mission

Apply the project's review rubric to every PR before merge. The rubric is non-negotiable: it lives in [`DEVELOPMENT.md`](../../DEVELOPMENT.md). The Review role's job is to *enforce* it consistently — not to invent new rules. This role can be filled by a human contributor or an AI agent; the rubric is the same either way.

`@pol-i-tech/leads` is the codeowner for `results/`, `compound-model/`, and `tools/` per `.github/CODEOWNERS`. This role inherits that ownership for those paths.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| The PR diff | `gh pr view <N> --json` | Primary input |
| The PR description | Same | Required to contain hypothesis + baseline + new metrics for refinement PRs |
| `DEVELOPMENT.md` "What reviewers check" list | [link](../../DEVELOPMENT.md#what-reviewers-check) | Canonical rubric |
| Validation CI result | GitHub Actions status | Blocks merge if failing |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Approval or change request | GitHub PR review | Binary |
| Inline comments | On specific files | Per finding |

## Allowed write paths

- GitHub PR reviews and comments only.

**Forbidden:** committing code on the PR's behalf. The Review role does not push fixes — it requests changes.

## Cadence

`per-PR` — every PR requires one approving review before merge per [DEVELOPMENT.md branch protection](../../DEVELOPMENT.md#contribution-workflow).

## Guardrails

The full rubric is [DEVELOPMENT.md "What reviewers check"](../../DEVELOPMENT.md#what-reviewers-check). Highlights:

- `methodology/` is present and runnable
- All subjective adjustments listed in `MODEL.md` with justification
- The model's approach matches what `MODEL.md` claims
- Backtest is walk-forward (no future data leakage)
- Outright/group markets sum to 1.0
- `tools/validate_predictions.py --all` passes

Plus the additional checks added by this catalog:

- For PRs labeled `refinement` or touching `methodology/<model>/`: the [refinement-loop protocol](refinement-loop.md) checklist (steps 1-7 in that doc).
- For PRs adding to `docs/agents/`: the new spec uses the [template](../../docs/agents/_role-template.md), all sections are non-empty, and it does not duplicate `DEVELOPMENT.md` rules (cite by reference).
- For PRs touching `results/<model>/`: writes are confined to that model's own subtree.
- If an automated orchestrator is ever re-enabled (see [`../ideation/2026-05-15-role-08-orchestration.md`](../ideation/2026-05-15-role-08-orchestration.md)), the `orchestrator/` branch prefix is allowed for its PRs (exception to the `<your-name>/<description>` convention). Today this is not in effect.
- `AGENTS.md` and `CLAUDE.md` stay in sync.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| PR author | Review with approve/request-changes verdict | per-PR |
| Merger (the PR author after approval, or codeowner) | Green light | per-PR |

## Escalation

- Stop and escalate if: a PR ships a parameter change without a CHANGELOG entry — close, do not merge.
- Stop and escalate if: a refinement PR backtested on the motivating tournament — close, do not merge.
- Stop and escalate if: an undocumented manual override appears in model code — request changes pointing to the [subjectivity policy](../../DEVELOPMENT.md#subjectivity-and-bias-policy).
- Stop and escalate if: a PR writes to another contributor's `results/<their-model>/` or `methodology/<their-model>/` — close, do not merge.

## Verification

- Every merged PR has at least one approving review.
- No PR merged with a failing `validate-predictions.yml` CI run.
- `DEVELOPMENT.md` rules are cited by section, not duplicated, in any role spec the reviewer approves.
- Stale reviews dismissed automatically on new commits — verified by GitHub branch protection settings, not the reviewer's discretion.
