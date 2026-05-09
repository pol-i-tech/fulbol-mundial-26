# 03 · Data Cleaning & Feature Engineering Agent

> Function-first agent: **raw → model-ready**. The only role allowed to write under `data/derived/`. All transforms, joins, fuzzy matches, name normalizations, freshness flags, and engineered features live here.

## Mission

Take immutable raw snapshots and emit normalized, joined, feature-engineered parquet files that every model can consume. This agent owns every transformation: name normalization to 3-letter FIFA codes, fuzzy player-name matching with explicit overrides, recency-decay weighting, missing-player fallbacks by position and tier, freshness flags, blended xG90 ratings, and team-level attack/pressing aggregates. Models read its outputs and only its outputs — they never see raw.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Raw snapshots | `data/raw/**` | All sources written by Data Engineering. |
| Player name overrides | `tools/player_name_overrides.py` | Manual mappings that must beat fuzzy match. |
| Country code dicts | `NAME_TO_FIFA3`, `ISO2_TO_FIFA3` in `tools/weekly_pull.py` | Source of truth for 3-letter codes. |
| Match importance weights | constants in `tools/weekly_pull.py` | `WC=1.0, Euro/Copa=0.9, WCQ=0.7, Nations=0.6, friendly=0.35` |

## Outputs

| Output | Path | Schema |
|---|---|---|
| StatsBomb player xG | `data/derived/statsbomb_player_xg.parquet` | per-player, per-tournament xG |
| StatsBomb team xG | `data/derived/statsbomb_team_xg.parquet` | per-match team-level xG |
| StatsBomb player summary | `data/derived/sb_player_summary.parquet` | per-player career rollup |
| StatsBomb player pedigree | `data/derived/sb_player_stats_pedigree.parquet` | tournament-weighted skill priors |
| Understat player xG | `data/derived/understat_player_xg.parquet` (+ `_raw`, `_2122`) | club-level player xG |
| Squad xG ratings | `data/derived/squad_xg_ratings.parquet` | `blended_xg90 = 0.4·national + 0.6·club` |
| Team attack ratings | `data/derived/team_attack_ratings.parquet` | nation-level attack signal |
| WC2026 squads (cleaned) | `data/derived/wc2026_preliminary_squads.csv`, `wc2026_final_squads.csv` | normalized FIFA codes |

## Allowed write paths

- `data/derived/**`
- `tools/aggregate_*.py`, `tools/build_*.py`, `tools/normalize_*.py`
- `tools/player_name_overrides.py`
- The `NAME_TO_FIFA3` / `ISO2_TO_FIFA3` constants in `tools/weekly_pull.py`

Forbidden: external HTTP (Data Engineering's job), `results/**`, `methodology/**`, `compound-model/**`.

## Cadence

- **Daily via Orchestrator**, immediately after Data Engineering completes its pulls.
- **On-demand** when raw snapshot fingerprints change for a non-cron source (e.g. a new StatsBomb tournament).

## Guardrails

- See [DEVELOPMENT.md — Architecture, Data flow](../../DEVELOPMENT.md#data-flow)
- See [DEVELOPMENT.md — Player Data Gap Plan](../../DEVELOPMENT.md#player-data-gap-plan) — fallbacks must be **documented**, not silent.
- See [DEVELOPMENT.md — Match importance weights](../../DEVELOPMENT.md#match-importance-weights-recency-decay)
- All overrides go in `tools/player_name_overrides.py`; do not bury them inside fuzzy-match code.
- Missing club xG must **not** silently equal national xG — use a documented fallback by position and tier and downgrade confidence.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Modeling / Data Science | `squad_xg_ratings.parquet`, `team_attack_ratings.parquet`, `statsbomb_team_xg.parquet`, `understat_player_xg.parquet` | Daily |
| Data Coverage | All `data/derived/*.parquet` | Daily |
| Edge / Comparison | Indirectly, via models | Daily |

## Escalation

- Stop and escalate if: the fuzzy-match acceptance rate for a nation drops **>10 percentage points** vs. last cycle.
- Stop and escalate if: any output parquet has `NaN` in a primary key.
- Stop and escalate if: `team_attack_ratings.parquet` does **not** cover all 48 WC2026 nations.
- Stop and escalate if: a manual override would silently overwrite a confident fuzzy match — surface a diff for human review first.

## Verification

- Every output parquet validates against its schema.
- No `NaN` in primary keys.
- `team_attack_ratings.parquet` has exactly 48 rows (one per WC2026 nation) with non-null `attack_rating`.
- `squad_xg_ratings.parquet`'s `blended_xg90` is finite and ∈ a documented range per position.
