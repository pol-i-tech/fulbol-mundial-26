# Acquisition: WC2026 Squads

## Mission

Maintain the canonical list of players each qualified nation will (or might) take to WC2026. Today this means scraping Wikipedia and any preliminary federation announcements; from FIFA's release on 2026-05-25, this means consuming official preliminary lists; from final-squad release through the confederation-finals exception (2026-05-30), this means consuming final 26-player rosters. Every player-level signal — Understat club xG, StatsBomb pedigree — is filtered through this list. **A wrong squad = wrong predictions.**

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Wikipedia squad pages | `https://en.wikipedia.org/wiki/<Country>_at_the_2026_FIFA_World_Cup` (and equivalents) | Pre-final, low-confidence |
| FIFA preliminary lists | TBD — official URL released ~2026-04 to 2026-05 | Authoritative once published |
| FIFA final-squad lists | TBD — official URL ~2026-05-25 | Final authority |
| Federation pages | Per-nation; links accumulate in `tools/pull_wc2026_squads.py` | Backup / earlier callup data |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Raw HTML cache | `data/raw/wikipedia/wc2026/<country>.html` | Upstream verbatim, dated |
| Preliminary squads | `data/derived/wc2026_preliminary_squads.csv` | One row per (nation, player); status field per [acquisition strategy Layer 2](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#layer-2-world-cup-candidate-pool) |
| Final squads | `data/derived/wc2026_final_squads.csv` | One row per (nation, player); only populated from 2026-05-25 |
| Squad attack ratings (joint) | `data/derived/squad_xg_ratings.parquet` | Joint output with Understat/StatsBomb |

## Allowed write paths

- `data/raw/wikipedia/wc2026/`
- `data/derived/wc2026_*.csv`
- `tools/pull_wc2026_squads.py`
- `tools/pull_wc2026_final_squads.py`

## Cadence

- `weekly` from now until 2026-05-25 — Wikipedia and federation page snapshots
- `daily` from 2026-05-25 to 2026-05-30 — confederation-final exception window means late changes
- `on-demand` after 2026-05-30 — only injury replacements per FIFA rules

## Guardrails

- See [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow).
- `squad_status` field must distinguish `historical_pool` / `recent_callup` / `preliminary` / `confirmed` / `excluded` — see [acquisition strategy Layer 2](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#layer-2-world-cup-candidate-pool).
- **Treating Wikipedia as final authority is forbidden once FIFA publishes preliminary or final lists.** This is in [DEVELOPMENT.md's source policy](../../DEVELOPMENT.md) by reference and called out in the [acquisition strategy "Avoid" section](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#source-policy).

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Compound-model](modeling-compound-model.md) | `wc2026_final_squads.csv` once available; `wc2026_preliminary_squads.csv` before | weekly until 2026-05-25, daily after |
| [Coverage Audit](quality-coverage-audit.md) | `wc2026_preliminary_squads.csv` for per-nation player count | weekly |
| Every player-level model | filtered to `squad_status in ('preliminary','confirmed')` after the cutoff | continuous |

## Escalation

- Stop and escalate if: a qualified nation has < 20 players in the preliminary squad (FIFA allows 35-55; below 20 is wrong).
- Stop and escalate if: FIFA publishes final squads and no consumer has been updated to use `squad_status='confirmed'` within 48h.
- Stop and escalate if: Wikipedia squad pages move or change format (the puller will fail; do not silently fall back to a stale snapshot).

## Verification

- `data/derived/wc2026_preliminary_squads.csv` has rows for every World Cup qualified team.
- After 2026-05-25, `wc2026_final_squads.csv` exists and each team has exactly 26 rows.
- `squad_status` column is populated for every row.
- Cross-check: every player in `wc2026_final_squads.csv` appears in `data/derived/player_registry.parquet` (when the registry exists; until then, a name-match audit suffices).
