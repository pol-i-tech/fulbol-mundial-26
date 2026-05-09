# 02 · Data Coverage Agent

> Function-first agent: **finds what we're missing**. Read-only. Detects gaps and staleness so the Data Engineering Agent knows what to chase next. The legacy `quality-coverage-audit.md` spec is a concrete implementation of this role.

## Mission

Produce one canonical, repo-tracked report of player- and team-level coverage gaps every cycle. The Coverage Agent never fixes data — it only reports. Its output is a prioritized worklist that drives the next Sunday's Data Engineering pulls and the next refinement pass for Modeling. Without this role, gaps compound silently and models drift toward whichever players happen to have rich data, regardless of whether they're even on a WC2026 squad.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Squad rosters | `data/derived/wc2026_preliminary_squads.csv` | Source of truth for who must be covered. |
| Squad xG ratings | `data/derived/squad_xg_ratings.parquet` | Output of the Cleaning Agent's fuzzy join. |
| StatsBomb player summary | `data/derived/sb_player_summary.parquet` | National-team minutes per player. |
| Understat club xG | `data/derived/understat_player_xg.parquet` | Club-side coverage signal. |
| Prior week's report | `data/derived/player_coverage_report.csv` | For week-over-week regression checks. |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Per-nation coverage report | `data/derived/player_coverage_report.csv` | `nation, squad_size, club_xg_matched, national_minutes_p50, stale_player_count, missing_player_names, generated_at` |
| Optional delta log | `data/derived/player_coverage_delta_<date>.md` | One-paragraph human summary if regressions appear. |

## Allowed write paths

- `data/derived/player_coverage_report.csv`
- `data/derived/player_coverage_delta_<YYYY-MM-DD>.md`
- `tools/audit_player_coverage.py`

Forbidden: `data/raw/**`, `methodology/**`, `results/**`, `compound-model/**`. Coverage never fixes data — it reports.

## Cadence

- **Daily via Orchestrator** as part of the 9:00 UTC cycle (`tools/audit_player_coverage.py`).
- **Per-PR** on PRs that touch `data/derived/` — surfaces silent regressions before merge.

## Guardrails

- See [DEVELOPMENT.md — Player Data Gap Plan](../../DEVELOPMENT.md#player-data-gap-plan)
- See [DEVELOPMENT.md — Current Priority Stack](../../DEVELOPMENT.md#current-priority-stack) — coverage is priority #2.
- Read-only contract: **no row may be added or removed from any input parquet by this agent**. Reviewers reject PRs from this role that touch derived data.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Orchestrator (priority routing) | `player_coverage_report.csv` | Daily |
| Data Engineering Agent (gap-fill) | `missing_player_names`, `stale_player_count` columns | When regression flags fire |
| Documentation / Learnings | `player_coverage_delta_<date>.md` | When deltas are non-trivial |

## Escalation

- Stop and escalate if: any nation in `wc2026_preliminary_squads.csv` is **missing entirely** from the report — indicates an input join failure.
- Stop and escalate if: a nation loses **>5 matched players week-over-week** without a corresponding squad change — likely a fuzzy-match regression in the Cleaning Agent.
- Stop and escalate if: `national_minutes_p50` drops to zero for a top-12 FIFA-ranked team — likely a StatsBomb pull failure.

## Verification

- `data/derived/player_coverage_report.csv` exists, is non-empty, and has one row per nation in `wc2026_preliminary_squads.csv`.
- No `NaN` in primary key columns.
- The script exits with code 0 when no regressions are detected, code 1 when a stop-condition fires (so CI can fail PRs).
