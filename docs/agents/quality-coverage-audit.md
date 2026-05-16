# Quality: Coverage Audit

## Mission

Make data-coverage gaps observable. Without an audit, the project's known weakness — uneven player coverage by region, league, freshness — stays invisible until a model produces an embarrassing prediction. This role refreshes a single canonical report every week, surfaces regressions, and emits a priority signal that drives Acquisition role work.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Squad xG ratings | `data/derived/squad_xg_ratings.parquet` | Player-grain joined data |
| Team attack ratings | `data/derived/team_attack_ratings.parquet` | Team-level aggregation |
| WC2026 squads | `data/derived/wc2026_preliminary_squads.csv` (when exists) or `data/derived/squad_xg_ratings.parquet` proxy | Denominator for coverage % |
| Prior week's report | `data/derived/player_coverage_report.csv` | For week-over-week regression detection |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Coverage report | `data/derived/player_coverage_report.csv` | One row per nation: `nation,players,matched_to_club,match_rate,national_minutes,low_minutes_players,missing_club_players,stale_players` |
| Audit script | `tools/audit_player_coverage.py` | Read-only on inputs, idempotent |

## Allowed write paths

- `data/derived/player_coverage_report.csv`
- `tools/audit_player_coverage.py`

**Forbidden:** modifying any acquisition-source file, any model output, or any other script.

## Cadence

`weekly` — runs as part of the Orchestrator's Sunday cycle, after acquisition pulls complete.

## Guardrails

- See [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow).
- See [`player-data-gap-plan.md` "Required Guardrails"](../plans/2026-05-06-player-data-gap-plan.md#required-guardrails).
- The script is **read-only on inputs**. Never modify acquisition data to "fix" coverage.
- Thresholds for `low_minutes_players` and `stale_players` documented in the script header; changing them is a methodology change requiring a PR (not a refinement-loop trigger because no model output changes).

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [International Results](acquisition-international-results.md), [StatsBomb](acquisition-statsbomb.md), [Understat](acquisition-understat.md), [WC2026 Squads](acquisition-wc2026-squads.md), [Elite-Club Form](acquisition-elite-club-form.md) | Priority signal (gap rows) | weekly |
| [Documentation/Learnings](synthesis-documentation-learnings.md) | Trend across weeks | weekly |
| [Data gaps roadmap](data-gaps-roadmap.md) | Promotes P1 → P0 when stop-conditions fire | weekly |

## Escalation

- Stop and escalate if: `match_rate` for any World Cup qualified team drops below 50% (promotes the relevant gap to P0 in the [data-gaps roadmap](data-gaps-roadmap.md)).
- Stop and escalate if: a previously-covered nation appears with zero players (suggests acquisition pipeline failure, not a real coverage drop).
- Stop and escalate if: input parquet schemas drift (script will fail loudly — that's intentional).

## Verification

- `python3 tools/audit_player_coverage.py` exits 0 against the current `data/derived/`.
- `data/derived/player_coverage_report.csv` exists with one row per nation present in `squad_xg_ratings.parquet`.
- Re-running the script produces a byte-identical file (idempotent).
- Each row has non-null values for all eight columns.

## Status

**Audit script lands in this PR.** First weekly run will establish the baseline; subsequent runs surface regressions.
