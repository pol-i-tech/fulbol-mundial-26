---
title: "feat: refresh squad-xG for top teams from 2026 rosters"
type: feat
status: active
date: 2026-06-11
---

# feat: refresh squad-xG for top teams from 2026 rosters

## Overview

The WC2026 sim's team attack/defense ratings are built from **2022–24 StatsBomb tournament participants**, not 2026 squads — and the ESPN 2026 roster scrape (2026-05-22) was missing 14 teams including **Spain, Netherlands, Uruguay, Morocco, USA, Ecuador**. Result: top teams are rated on stale personnel with thin club-xG coverage (Spain attack 0.32 vs France 0.67 despite FIFA parity; Netherlands undersold).

Today is matchday-1; squads are finalized and the live ESPN page now contains all teams. This plan re-pulls the rosters and recomputes team attack ratings from the real 2026 squads + current-club Understat xG, then propagates to the engine and re-runs the sim + report.

**Scope is deliberately the engine path** (`team_attack_ratings.parquet` → `raw.team_attack_ratings` → `curated.fact_team_rating`), which bypasses the player MDM-matching layer — so we fix what changes the prediction, fast and low-risk, without rebuilding the player master.

## Execution note — scope widened to ALL qualifiers during implementation

The plan was initially scoped to the FIFA top-16. During execution a top-16-only patch proved **invalid**: the roster-driven recompute lands on a different (club-weighted, less small-sample-inflated) scale than the old StatsBomb-tournament ratings, so patching only 16 teams while leaving the other 32 on the old scale would corrupt the engine's cross-team comparison. Because the sim compares all 48 qualifiers, the recompute was widened to **all 48 qualifiers on one consistent scale** (a strict improvement — 15 qualifiers previously had no rating and fell back to a median). The top teams are what we validate; everyone is recomputed for comparability.

## Requirements Trace

- **R1.** Re-pull 2026 squads so the missing top teams (ESP, NED, URU, MAR, USA, ECU) are present.
- **R2.** Recompute attack ratings for the top-16 from 2026 rosters + recent club xG (Understat) + national xG (StatsBomb), with the existing Bayesian shrinkage for thin samples.
- **R3.** Patch only the top-16 rows in `team_attack_ratings.parquet`; leave all other teams untouched.
- **R4.** Rebuild DuckDB, re-run the sim, regenerate the report; validate the top-16 ratings moved sensibly.
- **R5.** Be honest about residual gaps (players in leagues Understat doesn't cover keep national-only xG).

## Scope Boundaries

- **Only the FIFA top-16.** Other 32 teams keep their current ratings.
- **Engine path only.** We do **not** rebuild the player master / `fact_player_xg_per_90` MDM tables in this pass — so the report's *star-player narrative* may still show stale names for some teams. Deferred below.
- **No engine/weight changes.** Same ensemble, same Monte Carlo.
- **No new club-xG source.** Understat coverage limits stand (Eredivisie, Saudi, MLS, Brazil, Turkey not covered) → those players fall back to national xG + shrinkage.

### Deferred to Separate Tasks

- Full player-master MDM refresh so `fact_player_xg_per_90` (star-player narrative) reflects 2026 rosters for all teams.
- A non-Understat club-xG source (Sofascore/FBref) to close the structural league-coverage gap.

## Key Technical Decisions

- **Recompute at team level, patch the parquet.** `team_attack_ratings.parquet` feeds the engine directly and is keyed by nation (no surrogate-key matching), so patching the top-16 rows and rebuilding DuckDB updates `fact_team_rating` without disturbing the MDM player pipeline. Lowest blast radius for the time budget.
- **Roster-driven pool.** Build each top team's player list from the 2026 ESPN clean squad (`wc2026_squads_clean.parquet`: `display_name` + `club`), then attach club xG (Understat 2024, by normalized name) and national xG (`sb_player_summary`, by normalized name + nation). Reuse the existing attack proxy: mean blended xG/90 of the top-5 attackers, `blended = 0.4·national + 0.6·club` (national-only when no club match).
- **Reuse existing shrinkage constants** (`MIN_RELIABLE_MINS`, `PRIOR_XG90`, `PRIOR_MINS`) from `build_squad_xg_ratings.py` — no new modeling priors.

## Open Questions

### Resolved During Planning
- Source for fresh squads? → Live ESPN article (verified reachable today; now contains NED/ESP/URU).
- How to avoid destabilizing MDM? → Patch team-level parquet only; defer player-master refresh.

### Deferred to Implementation
- Exact normalized-name match rate for the new rosters vs Understat — measure during the run; report unmatched per top team.

## Implementation Units

- [x] **Unit 1: Re-pull + re-clean 2026 squads**

**Goal:** Get current rosters for all teams, including the missing top-16 ones.

**Files:**
- Run: `tools/pull_espn_wc2026_squads.py` → `data/raw/squads/espn/<today>/wc2026_squads.json`
- Run: `tools/build_wc2026_squads_clean.py` → `data/derived/wc2026_squads_clean.parquet`

**Approach:** Re-run the existing puller + cleaner unchanged. Verify NED, ESP, URU, MAR, USA, ECU now appear with non-empty `club`.

**Verification:** `wc2026_squads_clean.parquet` contains all top-16 teams, each with ~23–26 players and populated clubs.

- [x] **Unit 2: Roster-driven top-16 attack-rating recompute**

**Goal:** Corrected attack ratings for the top-16 from 2026 rosters, patched into the engine's input parquet.

**Files (as built):**
- Create: `tools/build_squad_xg_2026.py` (recomputes all 48 qualifiers; FIFA3-keyed via DB label maps)
- Modify (data): `data/derived/team_attack_ratings.parquet` (48 qualifier rows replaced, 19 non-qualifier rows kept byte-identical). `squad_xg_ratings.parquet` is **left untouched** — it feeds the player MDM, not the engine, so touching it was unnecessary and avoided.
- Test: `tools/tests/test_build_squad_xg_2026.py`

**Approach:**
- Load 2026 clean squads, filter to top-16. For each player: normalized-name join to Understat 2024 (club xG) and to `sb_player_summary` same-nation (national xG). Apply shrinkage. Compute `blended_xg90`.
- Team attack = mean blended of top-5; preserve the parquet's existing columns/schema so `build_duckdb.py` ingests it unchanged.
- Replace only the 16 nations' rows in both parquets; write back. Log per-team: players, club-match rate, old vs new attack.

**Test scenarios:**
- Happy path: each top-16 team yields a non-null attack rating from ≥5 players.
- Edge case: a player whose club isn't in Understat → national-only blended, no crash.
- Edge case: parquet schema (columns/dtypes) for patched rows matches untouched rows.
- Integrity: exactly the 16 nations' rows changed; all other nations byte-identical.

**Verification:** Spain/Netherlands attack ratings rise toward the contender range on football merit; non-top-16 teams unchanged.

- [x] **Unit 3: Rebuild, re-run, re-report, validate**

**Goal:** Propagate to the engine and regenerate outputs.

**Approach (as built):** A full `build_duckdb.py` rebuild is **blocked by a pre-existing, unrelated bug** — `db/masters/players.csv` has 17 columns (an `espn_player_id` added by the squads PR) but the `dim_player` loader still declares 16, so the CSV sniffer aborts. Rather than fix unrelated breakage under time pressure, the change was propagated **surgically**: reload `raw.team_attack_ratings` from the patched parquet and re-execute `db/sql/curated/fact_team_rating.sql` against the existing DB. This reaches the identical engine end-state (only `fact_team_rating.attack` changes; all other curated tables untouched). Then re-run the sim + report.

**Verification (done):** `fact_team_rating` attack reflects the new values; 19 non-qualifier parquet rows byte-identical; report regenerates deterministically; **Spain 3.6%→7.2%, Netherlands 4.3%→5.6%**, field compressed into a tight FIFA-elite race; all 55 tests pass.

**Follow-up flagged:** the `build_duckdb.py` ↔ `players.csv` 16-vs-17-column drift should be fixed so the full build path works again (separate PR).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| ESPN page structure changed → puller breaks | Verified reachable today; if parse fails, fall back to the existing `wc2026_squads.json` for present teams and pull only missing ones |
| DuckDB full rebuild perturbs other tables | Rebuild is the standard flow; validate non-top-16 ratings unchanged and all tests green |
| Name-match misses real stars | Log unmatched per team; roster `club` disambiguates; accept national-only fallback honestly |
| Report star-narrative still stale (MDM not refreshed) | Documented as deferred; engine (the prediction) is what this fixes |

## Sources & References

- Engine input: `tools/build_squad_xg_ratings.py` (proxy + shrinkage to reuse)
- Build wiring: `tools/build_duckdb.py` (`team_attack_ratings.parquet` → `raw.team_attack_ratings`)
- Roster source: live ESPN WC2026 squad article (id 48757621)
