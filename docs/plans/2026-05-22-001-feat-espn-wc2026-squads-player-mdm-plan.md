---
title: "feat: ESPN-Authoritative WC2026 Squads → Clean Player Master"
type: feat
status: active
date: 2026-05-22
---

# feat: ESPN-Authoritative WC2026 Squads → Clean Player Master

## Overview

ESPN's WC2026 squad-listing article publishes confirmed 26-man rosters for all 48 teams as nations finalize them (17 of 48 announced as of 2026-05-21, deadline 2026-05-29). It is the cleanest single-page roster source: per-team headings, position-bucketed sections (Goalkeepers / Defenders / Midfielders / Forwards), one player per link with a **stable ESPN player ID** in the URL, and a club in parentheses. This plan promotes ESPN to the **authoritative roster source** for the player master, demotes the existing Wikipedia scrapers to a fallback (and uses Wikipedia per-nation pages as a DOB enrichment join), and lands a deduplicated, pristine `db/masters/players.csv` plus a `data/derived/wc2026_squads_clean.parquet` that all downstream models can read.

After this plan, a downstream modeler can run a single query — `SELECT * FROM curated.dim_player WHERE country_code = 'MEX' AND is_active` — and get exactly the 26 players announced by ESPN, each carrying a stable `player_id` (across rebuilds), a persisted `espn_player_id` (across daily re-scrapes), a Wikipedia-derived `birth_date` where available, and the canonical FIFA team code.

## Problem Frame

The current player master is sourced from `data/derived/squad_xg_ratings.parquet`, a 1,275-row WC2026 *candidate pool* that predates final-squad announcements. It carries no DOB, no roster authority, and no stable third-party identifier beyond name + nation. Two consequences:

1. **Dedup is fragile.** Two players from the same nation with similar names cannot be told apart without DOB. Wikipedia DOB exists per-nation but isn't joined.
2. **No anchor across re-scrapes.** When a roster source updates, we rely on `(normalized_name, country_code)` to preserve `player_id`. Any name-spelling drift (`"Henry Martín"` vs. `"Henry Martin"`) risks reassigning IDs.

ESPN solves both: it carries a stable `espn_player_id` per player (in the URL path `.../id/<id>/...`), and its announcement reflects the official 26-man cut, so `is_active` is sharp instead of approximate. Wikipedia's per-nation pages cover DOB. Joining the two on `(normalized_name, country_code)` produces a clean, deduplicated, downstream-ready players table without paying for a third source.

## Requirements Trace

- R1. New `tools/pull_espn_wc2026_squads.py` writes immutable, dated raw snapshots under `data/raw/squads/espn/<YYYY-MM-DD>/wc2026_squads.json` capturing every announced team's full 26-man roster with `espn_player_id`, `name`, `position_bucket`, `club`, plus the team's `manager` and `announced_date`.
- R2. New `tools/build_wc2026_squads_clean.py` reads the latest ESPN snapshot, joins Wikipedia per-nation rosters from `data/raw/squads/wc2026_squads_confirmed.json` for DOB enrichment, and writes `data/derived/wc2026_squads_clean.parquet` (one row per announced player, deduplicated within team) and a `wc2026_squads_clean_collisions.csv` for human review.
- R3. `tools/refresh_player_master.py` is updated to prefer the clean parquet as the primary master source (Wikipedia JSON becomes fallback; `squad_xg_ratings.parquet` becomes second-fallback). A new `espn_player_id` column is added to `db/masters/players.csv` and used as a Tier 0 identity anchor across daily re-runs.
- R4. `player_id` assignments persist across the migration — every existing master row that matches an ESPN-announced player keeps its `P######`; the script writes `espn_player_id` back to the existing row, not a new one.
- R5. `curated.dim_player` exposes `espn_player_id` (nullable). `tools/verify_duckdb.py` asserts (a) `espn_player_id` is unique where non-null, (b) every announced WC2026-qualifier nation has between 23 and 26 active players in `dim_player`.
- R6. Downstream models (`ensemble_model.py`, `wc2022_xg_backtest.py`, `tools/build_2026_ratings.py`) continue to run unchanged — they read from `dim_player` / `fact_player_xg` and never depend on ESPN-specific columns. This plan does not modify model code.
- R7. The full pipeline is idempotent. Running the scraper twice in one day reuses cached HTML; running the clean-build twice produces identical parquet bytes; running the refresh twice produces an identical `players.csv`.
- R8. `db/SCHEMA.md` is updated to document the `espn_player_id` column and the new source-priority order. `docs/agents/01-data-engineering.md` registers ESPN as an Input.

## Scope Boundaries

- **In scope:** ESPN scraper, ESPN parser, Wikipedia DOB join, schema migration on `players.csv` (add `espn_player_id`), refresh-tool source-priority swap, `dim_player` column add, verify assertions, documentation updates.
- **Out of scope:**
  - ESPN player profile scraping (DOB via the per-player ESPN profile URL). Wikipedia DOB is sufficient for v1.
  - Any change to fact tables, matching layer, or model code. Tier 0 ESPN-ID matching for *stats sources* is meaningless until a stats source carries ESPN IDs — defer.
  - Caps / shirt-number / age columns — ESPN's article doesn't publish them, and we don't need them for matching or modeling.
  - Live in-tournament squad updates (Sofascore / API-Football) — covered by the separate `wc2026_live_pipeline_plan` in MEMORY.
  - Visualization or web export of the clean squad table.

### Deferred to Separate Tasks

- **ESPN profile DOB enrichment** — second-pass enricher that follows each ESPN player ID to its profile page when Wikipedia DOB join misses. Quoted as ~1,248 requests with polite delay; punt until Wikipedia coverage proves insufficient.
- **Wikipedia scraper retirement** — `tools/pull_wc2026_squads.py` and `tools/pull_wc2026_final_squads.py` stay as fallback for now. Once ESPN proves stable through tournament start, a follow-up can delete them.
- **ESPN-sourced player stats** — if/when a future plan adds ESPN team/player-stat ingestion, Tier 0 matching by `espn_player_id` becomes high-value; that plan rides on the column added here.

## Context & Research

### Relevant Code and Patterns

- `tools/pull_wc2026_squads.py:1-164` — existing Wikipedia all-squads scraper. Same shape (cached HTML in `data/raw/squads/`, BeautifulSoup parse, raw JSON + cleaned parquet outputs). New ESPN scraper mirrors its structure.
- `tools/pull_wc2026_final_squads.py:1-183` — existing per-nation Wikipedia scraper. Output `data/raw/squads/wc2026_squads_confirmed.json` is the **DOB source** for this plan. Schema: `{<nation>: [{name, position, club}, ...], "pending": [...]}`. Note: it does **not** currently parse DOB — Unit 2 of this plan augments its parse to also capture DOB from Wikipedia's per-nation table.
- `tools/refresh_player_master.py:104-178` — `load_source_from_parquet` and `load_source_from_json` are the two existing source loaders. Add a third (`load_source_from_clean_squads`) and reorder priority.
- `tools/lib/player_normalize.py:87-135` — `normalize()` and `normalize_country()` are the canonical name/country normalizers. ESPN parser uses both directly; no new normalization is invented.
- `db/SCHEMA.md` (lines describing `dim_player`) — column list authoritative; this plan adds one column.
- `db/sql/curated/dim_player.sql` — single-file SQL that builds `dim_player` from `db/masters/players.csv`; add `espn_player_id` column.
- `tools/verify_duckdb.py` — pattern for adding assertion categories.

### Institutional Learnings

- `MEMORY.md` → `feedback_player_identity_registry.md`: dims are sourced from authoritative masters; facts match to dims one-way; never silently extend masters from facts. ESPN as the authoritative roster source fits this exactly — it's not a fact, it's a roster declaration.
- `MEMORY.md` → `reference_curated_schema.md`: `db/SCHEMA.md` is the canonical contract — must be updated in lockstep with the column add.
- `docs/agents/01-data-engineering.md`: scrapers write under `data/raw/<source>/<date>/`, are idempotent on re-run within a day, must document URL and cadence in the script header.

### External References

- ESPN article URL: `https://www.espn.com/soccer/story/_/id/48757621/2026-world-cup-squad-lists-players-announced-all-48-teams`. Single-page HTML, no pagination, no auth. Structure (verified 2026-05-22):
  - H3 per group (`GROUP A`–`GROUP L`), H4 per team (with flag icon).
  - Per-team status line: `_Final squad was announced May 18_` (italicized; absent when not yet announced).
  - Four bolded position subheadings: `Goalkeepers:`, `Defenders:`, `Midfielders:`, `Forwards:`.
  - Player row: `[<name>](http://espn.com/soccer/player/_/id/<espn_player_id>/<slug>) (<club>)`.
  - Closing `Manager: <name>` per team.
  - "Roster yet to be announced" string used as the not-yet sentinel.

## Key Technical Decisions

- **ESPN is authoritative; Wikipedia is fallback + DOB.** ESPN gives a clean roster with stable IDs but no DOB. Wikipedia (already pulled) gives DOB but messier per-nation tables. Joining them on `(normalized_name, country_code)` gets both wins without a third source. Decided over "ESPN-only" because Tier 1 matching (with DOB) sharply improves dedup against StatsBomb/Understat downstream.
- **Persist `espn_player_id` on `dim_player`.** Pattern mirrors `understat_id` — a stable third-party ID kept as an identity anchor across re-scrapes. Lets the refresh tool short-circuit to "same player as yesterday" via Tier 0 on subsequent runs, immune to ESPN-side name normalization drift.
- **One row per (espn_player_id) within a team, even if names collide.** The ESPN ID is the definitive intra-source dedup key. If we ever observe two ESPN IDs producing identical `(normalized_name, country_code)` in the clean parquet, that's a real collision and goes to the human-review CSV — never silently merged.
- **`position_bucket` ∈ {GK, DF, MF, FW} stored alongside the existing free-form `position`.** ESPN's bucketing is cleaner than `squad_xg_ratings.parquet`'s compact `"M S"` / `"F"`-style codes. Both columns coexist: `position` keeps backward compat with existing models; `position_bucket` is the new clean field. No model code changes in this plan.
- **Schema migration on `players.csv` is additive only.** New column appended at the end; existing CSV consumers (the refresh tool, `dim_player.sql`) tolerate the addition. No row mutation beyond writing `espn_player_id` where matched.
- **Source priority for `refresh_player_master.py`:** `wc2026_squads_clean.parquet` (this plan's output) > `wc2026_squads_confirmed.json` (Wikipedia) > `squad_xg_ratings.parquet` (candidate pool). First non-empty wins.
- **Pending teams keep their candidate-pool rows active.** Until ESPN publishes a team, its existing `is_active=true` rows from `squad_xg_ratings.parquet` are preserved — we don't flip them inactive just because ESPN hasn't announced. The refresh tool's existing "untouched-during-this-run → inactive" sweep is scoped to **teams the current source covers**, not the whole master.

## Open Questions

### Resolved During Planning

- **ESPN role vs. Wikipedia?** Authoritative; Wikipedia kept as fallback + DOB enrichment (user-decided).
- **DOB strategy?** Pull DOB from Wikipedia per-nation pages (already scraped); no per-player ESPN profile fetches in v1 (user-decided).
- **Where does the ESPN scraper land in the agent org chart?** Role 01 (Data Engineering) — it's an external HTTP fetch, writing under `data/raw/squads/espn/<date>/`. The clean-build script is Role 03 (Data Cleaning), writing under `data/derived/`.
- **Do we need a new `data/raw/squads/espn/` subdirectory?** Yes — `data/raw/squads/` is currently flat with Wikipedia outputs. Nesting per-source under `data/raw/squads/<source>/<date>/` matches the convention in `docs/agents/01-data-engineering.md`.

### Deferred to Implementation

- **Wikipedia DOB selector resilience** — `pull_wc2026_final_squads.py`'s current regex doesn't extract DOB. Unit 2 needs to augment the per-nation parse, but Wikipedia tables vary slightly (some have "Date of birth (age)" combined, some separate). Final selector decided when looking at the cached HTML samples.
- **Exact dedup-collision threshold** — when does a `(country_code, normalized_name)` collision warrant a warning vs. a halt? Likely WARN only; final policy decided in Unit 6 verification.
- **Whether `manager` and `announced_date` belong on `dim_team` or stay parquet-only** — both are interesting but tangential. v1 keeps them in `wc2026_squads_clean.parquet` only; deferred to a follow-up if a model wants them.

## High-Level Technical Design

> *This illustrates the intended data flow and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
ESPN article (HTTP, daily) ─────────► data/raw/squads/espn/<date>/wc2026_squads.json
                                              │  (per-team: espn_player_id, name,
                                              │   position_bucket, club, manager,
                                              │   announced_date)
                                              ▼
Wikipedia per-nation pages (already pulled,    ┌────────────────────────────────┐
DOB regex added) ─► confirmed.json (+ DOB)  ──►│ build_wc2026_squads_clean.py  │
                                               │  - dedup within team by ESPN ID│
                                               │  - join Wikipedia DOB on        │
                                               │    (normalized_name, country)   │
                                               │  - emit collisions CSV          │
                                               └──────────────┬─────────────────┘
                                                              ▼
                                     data/derived/wc2026_squads_clean.parquet
                                              │
                                              ▼
                              tools/refresh_player_master.py
                                  (new source priority:
                                   clean.parquet > wiki.json > xg_ratings.parquet)
                                              │
                                              ▼
                                  db/masters/players.csv
                                  (+ espn_player_id column)
                                              │
                                              ▼
                                  build_duckdb.py → curated.dim_player
                                              │
                                              ▼
                          verify_duckdb.py asserts:
                          - espn_player_id unique where non-null
                          - announced teams have 23-26 active players
```

## Implementation Units

- [ ] **Unit 1: ESPN squad scraper**

**Goal:** Pull and cache the ESPN WC2026 squad-listing page; emit an immutable, dated raw JSON snapshot capturing every announced team's 26-man roster with stable ESPN player IDs.

**Requirements:** R1, R7

**Dependencies:** None

**Files:**
- Create: `tools/pull_espn_wc2026_squads.py`
- Create: `data/raw/squads/espn/<YYYY-MM-DD>/wc2026_squads.json` (script output; gitignored)
- Test: `tools/tests/test_pull_espn_wc2026_squads.py`

**Approach:**
- Mirror `tools/pull_wc2026_squads.py` shape: cached raw HTML, BeautifulSoup parse, raw JSON output.
- Cache key: `data/raw/squads/espn/<YYYY-MM-DD>/page.html`. On re-run same day, use cache; on a new day, fetch.
- Parse the H3 group headers, then H4 team headers, then the four bolded position subheadings. For each player row, extract `(espn_player_id, display_name, club)` via the link's `href` regex `/id/(\d+)/`. Capture per-team `announced_date` (the "_Final squad was announced May 18_" italic line) and `manager` (the "Manager: <name>" line).
- Skip teams whose section text contains `"Roster yet to be announced"`.
- Emit one JSON document with schema `{"as_of_date": "<YYYY-MM-DD>", "teams": [{"nation", "group", "announced_date", "manager", "players": [{"espn_player_id", "name", "position_bucket", "club"}]}]}`.
- Polite headers (`User-Agent: WC2026-research/1.0`), 1 request total per run.

**Patterns to follow:**
- Header block matching `tools/pull_wc2026_squads.py:1-30` — describes URL, cadence, outputs.
- Cached-fetch helper at `tools/pull_wc2026_squads.py:48-57`.

**Test scenarios:**
- Happy path: Given a fixture HTML containing groups A–C with 3 announced teams of 26 players each, parser emits exactly 3 team entries with 26 players each, each carrying a numeric `espn_player_id`.
- Happy path: A team's `announced_date` ("May 18") is captured as a string field; absent line → field is `null`.
- Edge case: A team section containing the literal "Roster yet to be announced" is skipped entirely (no entry in output).
- Edge case: A player line missing the parenthesized club ("[Name](url)" with no trailing `(club)`) yields `club = null`, not a parse error.
- Edge case: A duplicate `espn_player_id` within the same team's section (shouldn't happen, but if ESPN ever lists a player twice) is deduplicated with a WARN log.
- Error path: HTTP 5xx on first fetch raises and exits non-zero; cached HTML on retry produces deterministic output.
- Error path: Empty/truncated HTML (e.g. zero `<h4>` tags) exits non-zero with a clear error rather than silently emitting empty JSON.
- Integration: Cache hit on same-day re-run does not issue HTTP; output JSON byte-for-byte identical.

**Verification:**
- `python3 tools/pull_espn_wc2026_squads.py` writes today's JSON.
- Re-running same day issues zero HTTP requests and produces identical JSON.
- Output covers at least the 17 teams ESPN had announced as of 2026-05-21.

- [ ] **Unit 2: Wikipedia per-nation DOB extraction**

**Goal:** Augment `tools/pull_wc2026_final_squads.py`'s parser to capture `dob` per player from Wikipedia's per-nation squad table, so the downstream cleaner has a DOB enrichment join key. The script's outer behavior (which URLs it fetches, which JSON it writes) is unchanged.

**Requirements:** R2

**Dependencies:** None (independent of Unit 1; the Wikipedia HTML cache already exists in CI from prior runs).

**Files:**
- Modify: `tools/pull_wc2026_final_squads.py`
- Test: `tools/tests/test_pull_wc2026_final_squads.py`

**Approach:**
- Wikipedia squad tables include a column "Date of birth (age)" with values like `(1996-04-18) 18 April 1996 (age 30)`. Extend `parse_squad()` to capture this column when present and emit `dob` (ISO `YYYY-MM-DD`) on each player dict.
- Keep the existing position/name/club extraction unchanged. Tables that don't expose DOB simply emit `dob = null` for those rows — no halt.
- Existing output file `data/raw/squads/wc2026_squads_confirmed.json` gains an optional `"dob"` key per player entry. Schema-additive; old consumers tolerate the new key.

**Patterns to follow:**
- Same `pos_pattern` / row-pattern style already in the file (`tools/pull_wc2026_final_squads.py:67-114`).

**Test scenarios:**
- Happy path: Fixture HTML row containing `(1996-04-18) 18 April 1996 (age 30)` extracts `dob = "1996-04-18"`.
- Edge case: Row without a DOB column extracts everything else and emits `dob = null`.
- Edge case: Row with malformed date (`(1996-13-99)`) emits `dob = null` rather than raising.
- Edge case: A Wikipedia page where the DOB column appears in a non-standard position (different column order across nations) still extracts correctly — the parser keys off the column header, not column index.
- Integration: Re-running against an already-populated `wc2026_squads_confirmed.json` adds `dob` to existing player entries without dropping or reordering them.

**Verification:**
- Running the script populates `dob` on ≥60% of confirmed players (Wikipedia coverage typically high for confirmed squads).
- Existing tests for player count and position parsing still pass.

- [ ] **Unit 3: Clean squad builder (ESPN + Wikipedia DOB join)**

**Goal:** Produce the canonical, deduplicated `data/derived/wc2026_squads_clean.parquet` from the ESPN raw JSON, enriched with Wikipedia DOB. Surface intra-team collisions to a separate human-review CSV.

**Requirements:** R2, R7

**Dependencies:** Unit 1, Unit 2

**Files:**
- Create: `tools/build_wc2026_squads_clean.py`
- Create: `data/derived/wc2026_squads_clean.parquet` (script output)
- Create: `data/derived/wc2026_squads_clean.csv` (script output)
- Create: `data/derived/wc2026_squads_clean_collisions.csv` (script output; empty file when no collisions)
- Test: `tools/tests/test_build_wc2026_squads_clean.py`

**Approach:**
- Read the latest ESPN JSON (`data/raw/squads/espn/<latest-date>/wc2026_squads.json`). Find via directory listing, max by date.
- Read Wikipedia DOB-enriched JSON (`data/raw/squads/wc2026_squads_confirmed.json`).
- For each ESPN player, compute `normalized_name`, resolve `country_code` via `normalize_country(nation)`, and look up DOB in the Wikipedia map keyed on `(country_code, normalized_name)`.
- Dedup by `(country_code, espn_player_id)`. Within a team, if two distinct `espn_player_id`s normalize to the same `(country_code, normalized_name)`, emit both rows to the clean parquet (ESPN ID is the dedup key) and log the collision to the CSV. If the same `espn_player_id` appears twice from upstream, drop the dupe with a WARN.
- Add a `wiki_dob_match` boolean column for downstream visibility (true if Wikipedia provided a DOB, false otherwise).
- For teams listed in ESPN as not-yet-announced, no rows are emitted — those nations remain represented in the existing master via the `squad_xg_ratings.parquet` fallback path until announced.
- Output columns: `nation`, `country_code`, `confederation`, `group`, `espn_player_id`, `display_name`, `normalized_name`, `position_bucket`, `position` (free-form, copied from `position_bucket` for ESPN rows — full free-form values come from `squad_xg_ratings.parquet` only on the fallback path), `club`, `birth_date`, `birth_year`, `wiki_dob_match`, `manager`, `announced_date`, `as_of_date`.
- Confederation: lifted from `CONFEDERATION_MAP` in `tools/pull_wc2026_squads.py:28-45` — extract to `tools/lib/confederation.py` so the new builder doesn't import a sibling pull script.

**Patterns to follow:**
- `tools/build_squad_xg_ratings.py` for the "read raw, normalize, write parquet" shape (file header, CLI args, sort-and-write idiom).
- `tools/lib/player_normalize.py` for `normalize()` / `normalize_country()` — no new normalization logic.

**Test scenarios:**
- Happy path: 3 ESPN teams × 26 players + Wikipedia DOB for 60% → parquet has 78 rows, 47 with non-null `birth_date`, `wiki_dob_match` true for 47.
- Happy path: All output rows have non-null `country_code` (the `normalize_country()` call resolves all 48 WC2026 nation names from ESPN's display form, including `"USA"`, `"Türkiye"`, `"DR Congo"`).
- Edge case: Two ESPN player IDs in Mexico's roster normalizing to `"jose hernandez"` → both rows emitted, one collision row in CSV with both `espn_player_id`s listed.
- Edge case: ESPN player whose name has no Wikipedia DOB match (Wikipedia spells it differently, or that nation's Wiki page hasn't been pulled yet) → row emitted with `birth_date = null`, `wiki_dob_match = false`.
- Edge case: An ESPN nation name (e.g., `"USA"`) that `normalize_country()` does not resolve → halt with a clear error naming the unmapped nation, do not emit a row with `country_code = null` (this is the master-data-management rule: never silently extend identity).
- Error path: ESPN JSON missing or empty → exit non-zero with clear error message.
- Error path: Wikipedia JSON missing → proceed with `wiki_dob_match = false` everywhere; do not halt (Wikipedia is enrichment, not required).
- Integration: Running twice on the same inputs produces byte-identical parquet (deterministic row order: sort by `country_code`, then `espn_player_id`).

**Verification:**
- `python3 tools/build_wc2026_squads_clean.py` writes the parquet and CSV.
- Row count: 26 × (number of announced teams), ± edge cases.
- `wc2026_squads_clean_collisions.csv` is empty for the v1 happy path; manual inspection if not.
- Every row's `country_code` is a valid FIFA3 code present in `db/masters/teams.csv`.

- [ ] **Unit 4: Promote ESPN clean parquet as primary source in `refresh_player_master.py`**

**Goal:** Rewire `refresh_player_master.py` so the clean parquet is the primary roster source. Add `espn_player_id` column to the master schema and use it as a Tier 0 identity anchor across daily re-runs.

**Requirements:** R3, R4, R7

**Dependencies:** Unit 3

**Files:**
- Modify: `tools/refresh_player_master.py`
- Modify: `db/masters/players.csv` (schema-additive: one new column at end)
- Modify: `db/SCHEMA.md` (document new column and source priority)
- Test: `tools/tests/test_refresh_player_master.py`

**Approach:**
- Add `espn_player_id` to `MASTER_COLUMNS` (`tools/refresh_player_master.py:57-74`), positioned after `understat_id` to group third-party identifiers together.
- Add `load_source_from_clean_parquet(path)` — reads `data/derived/wc2026_squads_clean.parquet`, returns rows dict-shaped identical to the existing loaders but with an extra `espn_player_id` key.
- Modify `main()`'s source-priority logic (`tools/refresh_player_master.py:340-352`): clean parquet first, then Wikipedia JSON, then `squad_xg_ratings.parquet`. Track which source supplied each row.
- Add Tier 0 to `find_existing()` (`tools/refresh_player_master.py:181-196`): when the source row carries an `espn_player_id`, first look up the master by `espn_player_id`. Single match → use that row. Multiple matches (shouldn't happen) → log and skip. Zero matches → fall through to the existing Tier 1/2 logic.
- `update_master_row()` learns to write `espn_player_id` to the matched row when the source carries one and the master row currently has it blank. Never overwrite a non-blank `espn_player_id` with a different value — surface as WARN and skip the write (real collision needing human review).
- The inactive-marking pass (`tools/refresh_player_master.py:301-308`) is scoped to **teams covered by this source**. If the source only covers 17 teams' worth of players, only existing master rows for those 17 nations are eligible to be marked inactive. Pending nations' candidate-pool rows stay `is_active=true` until ESPN announces them.
- After Unit 5's backfill, this becomes the daily-refresh path during the May 22 → May 29 announcement window.

**Patterns to follow:**
- The two existing source loaders at `tools/refresh_player_master.py:104-178` for the shape of `load_source_from_clean_parquet`.
- The existing `derive_birth_year()` usage for parsing `birth_date`.

**Test scenarios:**
- Happy path: First run against a clean parquet (17 announced teams × 26 = 442 players) on a master that already has matching `P######` rows from the candidate-pool source → existing IDs preserved, `espn_player_id` written to each matched row.
- Happy path: Second run same day → all 442 rows hit Tier 0 (espn_player_id match), no new IDs assigned, no field changes, `unchanged = 442`.
- Edge case: ESPN player whose normalized name + country_code exists in master with `espn_player_id` blank → Tier 0 miss falls to Tier 2; existing row updated and `espn_player_id` written.
- Edge case: ESPN player not in master at all (new face, fresh debut) → new `P######` assigned, with `espn_player_id` populated and `birth_date` from Wikipedia where available.
- Edge case: Master row carries `espn_player_id = "12345"` but the new source has `espn_player_id = "67890"` for the same `(normalized_name, country_code)` — WARN logged, no write, ambiguous counter increments.
- Edge case: Player drops out of ESPN's 26-man cut between yesterday's and today's run → `is_active = false`; `player_id` and `espn_player_id` preserved. Player can come back later (injury replacement) → `is_active = true` restored, same `player_id`.
- Edge case: A nation that ESPN has not yet announced — none of its candidate-pool rows are flipped to inactive; the scoped sweep ignores them.
- Error path: Clean parquet missing → loader returns empty; falls back to Wikipedia JSON loader. Both empty → falls back to `squad_xg_ratings.parquet`. All three empty → existing error-and-exit-1 behavior.
- Integration: A full pipeline run `pull_espn_wc2026_squads.py → build_wc2026_squads_clean.py → refresh_player_master.py → build_duckdb.py → verify_duckdb.py` exits 0 and produces a `dim_player` with the expected announced-team counts.

**Verification:**
- `db/masters/players.csv` gains exactly one new column (`espn_player_id`); row count unchanged on first run beyond newly-announced players.
- Re-running same day produces no diff in `players.csv` (idempotency).
- A spot-check of three nations (e.g., Mexico, Argentina, Brazil) shows exactly 26 active players each with non-null `espn_player_id` after the announcement.

- [ ] **Unit 5: One-shot backfill + collision audit**

**Goal:** Run the new refresh against the current 1,275-row master, write `espn_player_id` onto every matched row, generate an audit CSV of unmatched master rows (and unmatched ESPN rows), and commit the updated `players.csv`. This is the migration moment — after this unit, the pristine clean players table exists.

**Requirements:** R3, R4

**Dependencies:** Unit 4

**Files:**
- Modify: `db/masters/players.csv` (data update, not schema — Unit 4 already added the column)
- Create: `data/derived/player_master_backfill_audit_2026-05-22.csv` (audit artifact; one-shot, dated)
- Create: `docs/solutions/best-practices/espn-player-master-migration-2026-05-22.md` (record the migration, what was matched, what was quarantined)

**Approach:**
- Run `python3 tools/refresh_player_master.py --master-path db/masters/players.csv` after Units 1–4 are in place and the clean parquet exists.
- Diff the new `players.csv` against the old, partitioned by:
  - **Matched + ESPN ID written** (expected majority): existing `player_id`, gained `espn_player_id`, possibly gained `birth_date` from Wikipedia DOB join. No `player_id` mutations.
  - **Newly-added rows** (ESPN players not in candidate pool, e.g. fresh international debuts): new `P######` assigned, `espn_player_id` populated.
  - **Master row that ESPN does not cover** (candidate-pool player who didn't make the 26-man cut, OR nation not yet announced): `player_id` preserved; `is_active` depends on whether nation is announced (announced → false; pending → true).
- Write the audit CSV with columns `player_id`, `display_name`, `country_code`, `category`, `espn_player_id`, `notes` so a human can review the migration before commit.
- Write the solution doc capturing: counts per category, any ambiguous matches that needed manual override, the WARN log if any collisions occurred.

**Patterns to follow:**
- `docs/solutions/best-practices/` style — YAML frontmatter (`module`, `tags`, `problem_type`), then prose. See `model-roles-and-best-use-2026-04-28.md` for shape.

**Test scenarios:**
<!-- This is a one-shot operational unit, not a code unit. Test scenarios scope to the audit assertions. -->
- Happy path: The audit CSV's "Matched + ESPN ID written" partition includes ≥80% of ESPN players (the rest land in "Newly added" or "Ambiguous").
- Happy path: No `player_id` from the prior master is missing in the new master — every `P######` is preserved.
- Edge case: At least one nation (e.g., a CAF qualifier with regional naming variance) shows a >5% ambiguity rate → flagged for manual override.
- Error path: If any `player_id` mutation occurs (a stable ID got reassigned), the audit halts and rolls back — `player_id` immutability is the project's hardest invariant.

**Verification:**
- New `players.csv` has identical `player_id` set ± newly-added rows compared to the prior commit.
- `espn_player_id` populated on ≥80% of `is_active=true` rows for ESPN-announced nations.
- Audit CSV committed; solution doc committed.

- [ ] **Unit 6: `dim_player` column + verification assertions + docs**

**Goal:** Wire `espn_player_id` through to `curated.dim_player`, add DuckDB verification assertions for the new column and for per-team active counts, and update the human-readable docs that describe the data model and the agent org chart.

**Requirements:** R5, R8

**Dependencies:** Unit 5

**Files:**
- Modify: `db/sql/curated/dim_player.sql`
- Modify: `tools/verify_duckdb.py`
- Modify: `db/SCHEMA.md` (column registered earlier in Unit 4; this unit adds the verify-assertion section)
- Modify: `db/README.md`
- Modify: `docs/agents/01-data-engineering.md` (add ESPN to Inputs table)
- Modify: `docs/agents/03-data-cleaning.md` (add the new clean parquet to Outputs)
- Create: `db/queries/examples/squad_by_team.sql` — `SELECT * FROM curated.dim_player WHERE country_code = ? AND is_active`
- Test: `tools/tests/test_verify_duckdb.py` (extend existing tests with the new assertions)

**Approach:**
- `dim_player.sql`: add `espn_player_id VARCHAR` to the column list. Verify against `db/masters/players.csv`'s new column.
- `verify_duckdb.py`: add two assertion categories:
  1. **`espn_player_id` uniqueness** — `SELECT espn_player_id, COUNT(*) FROM curated.dim_player WHERE espn_player_id IS NOT NULL GROUP BY 1 HAVING COUNT(*) > 1` must return zero rows. FAIL on violation.
  2. **Announced-team active counts** — for each nation where ESPN's clean parquet had ≥1 player, `SELECT COUNT(*) FROM curated.dim_player WHERE country_code = ? AND is_active` must return a value in `[23, 26]`. WARN (not FAIL) on edge; FAIL only if count is zero (means matching collapsed).
- `db/SCHEMA.md`: add `espn_player_id` to the `dim_player` column table; document the new source-priority order under "Source provenance"; add the two new assertions to the verify-script section.
- `db/README.md`: brief paragraph on the ESPN → Wikipedia DOB → master flow; pointer to the example query.
- `docs/agents/01-data-engineering.md`: add row to Inputs table: `ESPN WC2026 squads | https://www.espn.com/soccer/story/_/id/48757621/... | Daily May 22 → May 29; on-demand thereafter`.
- `docs/agents/03-data-cleaning.md`: add `data/derived/wc2026_squads_clean.parquet` to Outputs.

**Patterns to follow:**
- Existing `db/sql/curated/dim_player.sql` column declarations.
- Existing assertion blocks in `tools/verify_duckdb.py` (row-count bounds and FK integrity blocks are the template).
- `db/queries/examples/` SQL files for the example query style — see `db/SCHEMA.md`'s reference.

**Test scenarios:**
- Happy path: After a full build, `verify_duckdb.py` exits 0 and prints both new assertions as PASS.
- Edge case: Manually inject a duplicate `espn_player_id` into `players.csv`, rebuild — verify exits non-zero with the uniqueness FAIL message.
- Edge case: Inject a nation with 22 active rows — verify exits 0 with a WARN line; with 0 active rows — verify exits non-zero with FAIL.
- Integration: The example query `SELECT * FROM curated.dim_player WHERE country_code = 'MEX' AND is_active` returns exactly 26 rows after Mexico's roster lands.

**Verification:**
- `python3 tools/build_duckdb.py && python3 tools/verify_duckdb.py` exits 0.
- Spot-check three nations: row count in `[23, 26]`, all non-null `espn_player_id` on `is_active=true` rows.
- All modified docs render correctly (no broken links, no stale column lists).

## System-Wide Impact

- **Interaction graph:** ESPN scraper is a new entry point; the existing daily orchestrator (`08-orchestration` role, daily 09:00 UTC) gains a new step before `refresh_player_master.py`. No existing scraper changes its outputs.
- **Error propagation:** ESPN scraper failures (network, schema drift) must not halt the rest of the daily pipeline — refresh tool's existing fallback chain (clean parquet → Wikipedia JSON → candidate-pool parquet) absorbs the absence. Verify-script WARNs surface ESPN gaps but don't FAIL the build.
- **State lifecycle risks:** The schema-additive change to `players.csv` is the riskiest moment. If any reader (downstream parquet consumer, an old test) pins to a column count rather than column names, the addition could break it. Mitigation: all known readers in this repo key off column names; the test suite covers it.
- **API surface parity:** `dim_player` gains one column. All existing SQL queries that `SELECT *` still work; queries that enumerate columns explicitly continue to work as long as they don't assume column ordinality. No model code reads `dim_player` directly today; it reads through `fact_player_xg` joins.
- **Integration coverage:** Unit 4's full-pipeline integration test (scraper → builder → refresh → duckdb → verify) is the only place we prove the seam between the new clean parquet and `dim_player`. Without it, mocks in unit tests can pass while the seam silently breaks.
- **Unchanged invariants:**
  - `player_id` (`P######`) is never reassigned. Unit 5 explicitly halts if it observes a reassignment.
  - `fact_player_xg` schema unchanged; existing matched StatsBomb/Understat rows continue to join cleanly.
  - The MDM rule from `MEMORY.md` (dims sourced from authoritative masters, facts match one-way to dims) is reinforced, not bent.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| ESPN changes the article's HTML structure mid-window (May 22 → May 29) | Snapshot today's cached HTML as a parser fixture; Unit 1 test runs against the fixture; the existing Wikipedia fallback path remains live, so a parser break degrades gracefully. |
| Wikipedia DOB extraction misses a high share of players because per-nation table shapes differ | `wiki_dob_match` boolean column makes coverage measurable; if <50% match overall, escalate to the deferred ESPN-profile DOB enricher. |
| ESPN spells a nation name (`"USA"`, `"Türkiye"`, `"Czechia"`, `"DR Congo"`) such that `normalize_country()` returns None | Unit 3 halts with a clear error rather than emitting NULL country_code. Add any unmapped names to `_DB_LAYER_NAME_SUPPLEMENT` in `tools/lib/player_normalize.py` as encountered. ESPN's display forms are checked against the existing mapping during Unit 1's first real run. |
| Backfill (Unit 5) accidentally reassigns a `player_id` due to a normalization edge case | Unit 5's test scenarios include an explicit "no `player_id` mutation" assertion that halts and rolls back on violation. |
| `espn_player_id` collisions across teams (same ID appears for two different players in different nations) | Verify assertion 1 in Unit 6 detects this and FAILs the build. Should be impossible given ESPN's ID scheme, but worth catching. |
| 26-man cut means some candidate-pool players from `squad_xg_ratings.parquet` move to `is_active=false` and downstream models that filter `is_active` lose them | Existing models read `fact_player_xg` (which joins `player_id`, not `is_active`), so this is a no-op for current modeling. The risk surfaces only if a future query adds an `is_active` filter to a player-history aggregation; flag in Unit 6 docs. |

## Documentation / Operational Notes

- **Cadence:** During announcement window (now → 2026-05-29), run `pull_espn_wc2026_squads.py` daily; the orchestrator schedules this. After 2026-05-29, drop to weekly until tournament start (2026-06-11), then on-demand.
- **Rollout:** Land Units 1–3 as one PR (the new pipeline, behind no flag — the clean parquet just becomes a new derived output). Units 4–6 as a second PR (the master refactor + dim_player column + verification). Unit 5 is the runtime migration moment inside PR 2.
- **Monitoring:** Verify-script WARN counts get surfaced in the daily orchestrator's PR comment per `docs/agents/08-orchestration.md`. A sudden drop in `wiki_dob_match` coverage or a spike in collision-CSV row count are the early-warning signals.
- **Rollback:** Revert the two PRs in order. `players.csv` schema additions are forward-compat with old readers; removing the column on rollback just drops the data. `player_id` immutability is preserved regardless of rollback.

## Sources & References

- **ESPN article (data source):** [https://www.espn.com/soccer/story/_/id/48757621/2026-world-cup-squad-lists-players-announced-all-48-teams](https://www.espn.com/soccer/story/_/id/48757621/2026-world-cup-squad-lists-players-announced-all-48-teams)
- **Existing player MDM plan:** [docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md](2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md)
- **Player data acquisition strategy:** [docs/plans/2026-05-06-world-cup-player-data-acquisition-strategy.md](2026-05-06-world-cup-player-data-acquisition-strategy.md)
- **Schema contract:** [db/SCHEMA.md](../../db/SCHEMA.md)
- **Data Engineering agent spec:** [docs/agents/01-data-engineering.md](../agents/01-data-engineering.md)
- **Data Cleaning agent spec:** [docs/agents/03-data-cleaning.md](../agents/03-data-cleaning.md)
- **MDM principle (memory):** `feedback_player_identity_registry.md` — dims sourced from authoritative masters; facts match to dims one-way.
- **Curated schema reference (memory):** `reference_curated_schema.md` — `db/SCHEMA.md` is canonical.
