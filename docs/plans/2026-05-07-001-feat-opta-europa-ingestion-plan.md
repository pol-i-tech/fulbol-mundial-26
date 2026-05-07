---
title: "feat: Ingest Opta Europa dataset and wire into statistical models"
type: feat
status: active
date: 2026-05-07
---

# feat: Ingest Opta Europa dataset and wire into statistical models

## Overview

A 20 GB compressed Opta dataset (`europa.zip`, 296 GB uncompressed) covering **70+ European competitions** — top 5 leagues, all secondary divisions, every major domestic cup, UCL / Europa League / Conference League, **WC qualifiers**, Nations League, Euros, U17/U19/U21, and 18 seasons of history per league — has been acquired and sits at `~/Downloads/europa.zip`. The dataset is per-match summary level (goals, cards, subs, VAR + 105 team and 120 player season aggregates) but **does not contain xG**.

This plan describes how to (1) keep the dataset on the workstation without exhausting disk, (2) wrangle it into a small, model-ready set of parquet tables under `data/derived/`, (3) reconcile it with the existing Understat / martj42 / squad sources, and (4) wire it into the statistical model layer. The goal is that the existing Dixon-Coles model, the form-recency feature, the upcoming "last N matches per player" deliverable, and any new model can pull from these parquets the way they already pull from `statsbomb_team_xg.parquet` today.

## Problem Frame

Three pressures forced this plan:

1. **Coverage**: `tools/pull_understat_players.py` covers only 6 leagues (top 5 European + RFPL) and Understat is league-only. UCL, every domestic cup, WC qualifiers, Nations League, smaller European leagues — every one of those is a coverage gap today. The Opta dataset closes all of them.
2. **Disk reality**: The full extract is **296 GB**, the workstation has **223 GB free**. Full extraction is impossible. We need a mechanism that preserves access to all 334,026 files without ever putting them all on disk simultaneously.
3. **License**: Opta data is enterprise-licensed and cannot be redistributed publicly. The repo's gitignore already covers `data/raw/` so the source file stays local; that's fine. But anyone reproducing this needs their own copy — which means the documentation must describe the provenance precisely.

The "no xG" finding is a real ceiling on what this dataset alone enables. It does not replace Understat for xG-based features. It does add cup/UCL/international fixtures, goals/shots/possession/cards/subs at match granularity, and broad-coverage season aggregates — the value is in *coverage*, not in *expected goals*.

## Requirements Trace

- R1. The 20 GB zip is the canonical raw artifact. Lives at `data/raw/opta-europa/<YYYY-MM-DD>/europa.zip`. Never extracted in full.
- R2. A zip-aware utility module exposes one function call `read_member(path) -> bytes | dict | DataFrame` so wrangler scripts read individual files lazily without extracting the archive.
- R3. A file manifest parquet at `data/derived/opta_manifest.parquet` lists every file in the zip with `(competition, season, team, file_kind, byte_size, member_path)` so downstream code can locate any record without re-walking the zip.
- R4. Five model-ready derived parquets under `data/derived/`:
  - `opta_match.parquet` — one row per match (date, teams, scores, competition, venue, status)
  - `opta_match_event.parquet` — one row per discrete event (goal, card, substitution, VAR), keyed to match
  - `opta_team_season.parquet` — one row per (team, competition, season) with all 105 team aggregates
  - `opta_player_season.parquet` — one row per (player, team, competition, season) with all 120 player aggregates
  - `opta_player_match.parquet` — one row per (player, match) for every player who appeared, with minutes-played, goals, assists, cards (derived from events + squad)
- R5. Cross-source ID resolution: every WC2026 player from `data/derived/wc2026_squads.parquet` resolves to (a) Opta `player_id` and (b) Understat `player_id` where available, written to `data/derived/player_id_crosswalk.parquet`.
- R6. Idempotent: re-running the wrangler from the same zip produces byte-identical parquets (deterministic sort, stable hashing).
- R7. The pipeline plugs into `tools/weekly_pull.py` so the standard refresh re-derives Opta-backed parquets when the zip changes.
- R8. The existing freshness validator (per the data-capture plan) gains four new file checks.
- R9. The Dixon-Coles fit and the new "last N matches per player" deliverable consume the Opta parquets — Opta team-season aggregates feed prior strength estimates; Opta player-match appearances feed form-recency features for non-Understat-league players.
- R10. Documentation: `methodology/_opta-ingestion/README.md` describes the source, license constraint, schema, and how to obtain the zip (so a contributor can reproduce).

## Scope Boundaries

- **Not** decompressing the full archive. The zip stays the source of truth.
- **Not** computing xG from this dataset. It does not have shot-level locations, situations, or any expected-goals model output.
- **Not** publishing the source data. License-restricted.
- **Not** rewriting existing scripts that consume Understat or StatsBomb — those stay; Opta is *additive*.
- **Not** committing any extracted JSON. Only the wrangler scripts and small derived parquets are produced; nothing in `data/raw/` or `data/derived/` enters git.
- **Not** building a streaming/incremental update system for now. Opta-source updates are quarterly at best; full re-build of derived parquets is acceptable.

### Deferred to Separate Tasks

- Building a homegrown xG model fed by this dataset's match summary. Would need shot-level data this dataset doesn't have, so a separate sourcing exercise comes first.
- Migrating the manifest+wrangler pattern to a database (DuckDB / SQLite). Parquet is enough at this volume.
- Multi-language player-name reconciliation across Cyrillic / Greek / Turkish character sets — Phase 2.

## Context & Research

### Verified facts about the dataset (probed 2026-05-07)

- **Source**: Opta basic stats feed, scraped from `scoresway.com` (URLs visible in CSVs); IDs follow Opta's UUID format (`d1bx99scogod2lz819u36qmfo`).
- **Compression**: 20 GB zip → **296 GB extracted, 334,026 files**.
- **Structure**: `testeo_ligas_europa/<competition>/<season>/equipos/<team>/jsons/{matches_equipo,seasonstats,squad}.json` plus team-level `<team>_jugadores.csv` rosters.
- **Per-match content** (from one Played match — Manchester United vs Arsenal, 2025-03-09):
  - `matchInfo`: id, dates, week, competition, contestants, venue, officials
  - `liveData.matchDetails`: matchStatus (Played/Fixture), scores (HT/FT), winner, period start/end timestamps, match length
  - `liveData.goal`: array of goals with scorer_id, scorer_name, assist_id, assist_name, time_min_sec, period_id
  - `liveData.card`: array of cards with player_id, type (YC/RC/2YC), reason, time_min_sec
  - `liveData.substitute`: array of subs with player_on_id, player_off_id, time_min_sec
  - `liveData.VAR`: array of VAR decisions
  - `liveData.matchDetailsExtra`: attendance, list of officials
- **Per-team-season**: 105 aggregate stats (Goals, Possession Percentage, Passing Accuracy, Total Shots, Goal Conversion, Clean Sheets, etc.) under `contestant.stat[]`.
- **Per-player-season**: ~120 aggregate stats per player under `player[].stat[]`, plus identity fields (player_id, position, dorsal, firstName, lastName, country).
- **Confirmed absent**: `xG`, `Expected Goals`, `xA` — searched all 105 team stat names and all 120 distinct player stat names; zero matches.
- **Coverage** (as of 2026-05-07 probe):
  - All top 5 European leagues + 30+ smaller leagues
  - UEFA Champions League / Europa League / Conference League / Super Cup / Nations League / Euros / Euro Qualifiers / **WC Qualifiers** / U17/U19/U21
  - All major domestic cups (FA Cup, Coppa Italia, Copa del Rey, DFB-Pokal, Coupe de France, KNVB Beker, etc.)
  - Recent seasons (2024-25, 2025-26) fully populated; older seasons coverage varies by league
  - WC Qualifiers folder includes per-nation `matches_equipo.json` for all 48+ nations

### Relevant code and patterns

- `tools/pull_statsbomb.py` — pattern: pull → cache raw JSON → flatten to per-team and per-player parquet. The Opta wrangler will follow the same shape but read from a single zip rather than per-match HTTP.
- `tools/build_squad_xg_ratings.py` — pattern: load multiple parquets, fuzzy-name-match, write derived. The cross-source ID crosswalk in R5 follows this pattern.
- `tools/weekly_pull.py` — orchestrator. Already wires Kalshi, Polymarket, Elo. Opta wrangler joins this list, gated by zip presence.
- The existing data-capture plan (`docs/plans/2026-05-06-001-fix-data-cleanse-games-teams-players-plan.md`) covers Understat per-match xG and the unified `player_last_n_matches.parquet`. This Opta plan **completes** that one — both feed the same final deliverable.

### External references

- Opta documentation is gated behind enterprise license; we work from observed schema rather than docs.
- Scoresway URL pattern present in CSVs: `https://www.scoresway.com/en_GB/soccer/<league>/...`
- Public DEVELOPMENT.md "Subjectivity and bias policy" applies — any feature derived from this dataset gets documented in MODEL.md sections.

## Key Technical Decisions

- **Zip-as-source-of-truth, no full extraction.** A `zipfile.ZipFile` instance held open by the wrangler reads members lazily. Parsed JSON is converted to flat rows in-memory and appended to a list of dicts; that list is written once per derived table. Memory peak per table ≤ 2 GB even for the largest derived. Rationale: the laptop has 223 GB free; full extraction needs 296 GB; selective re-extraction would need careful caching. Stream-from-zip is simplest and fastest.

- **Five derived parquets, not one.** Different join keys, different update frequencies, different sizes. Splitting by grain matches how downstream models consume the data and avoids wide-and-sparse rows (the season-stat parquets have ~120 columns; the match parquets have ~25). Rationale: mirrors the existing `statsbomb_team_xg` / `statsbomb_player_xg` split.

- **Manifest as a separate first-class output.** A small parquet listing every file in the zip is the navigation index for the wrangler and for any ad-hoc analysis. Build it once; rebuild only when the zip changes. Rationale: a 334,026-file zip is too big to walk repeatedly.

- **All 105/120 stat columns retained, normalized snake_case.** No subjective filtering of which stats matter — that's a model decision, not an ingestion decision. Column-rename rule: lowercase, strip parentheticals, replace spaces and special chars with underscores, collapse repeated underscores. Documented in `methodology/_opta-ingestion/`. Rationale: future models may need stats this plan can't predict; storage cost of extra columns is negligible at parquet+zstd.

- **Player-match appearance derivation from events + squad.** `opta_player_match.parquet` is built by combining `liveData.substitute[]` events with the matchday squad list (in `squad.json` per team-season). Players who started + were never subbed off play `match_length_min`; players subbed on at minute X play `match_length_min - X`; players in the squad but never appearing in any event are *not* in the file. Rationale: minutes are the most-used model feature; getting them right enables the recency-weighted form features that prior plans referred to.

- **Player ID crosswalk lives in its own parquet.** `data/derived/player_id_crosswalk.parquet` resolves `(wc2026_squad_player) ↔ opta_player_id ↔ understat_player_id`. Built once per refresh by fuzzy-name + club-context match. Rationale: every downstream join needs it; centralising the crosswalk avoids per-script reinvention.

- **Wrangler is one orchestrator + per-table builders.** `tools/build_opta_derived.py` is the entry point; `tools/_opta_zip.py` is the shared zip reader; per-table builders `tools/_opta_<table>.py` produce one parquet each. Rationale: each builder is independently testable and re-runnable.

- **Competition kind taxonomy.** Map every competition to one of `domestic_league | domestic_cup | european_uefa | international` so model code can filter without parsing free-form names. Hard-coded dict in `tools/_opta_competitions.py`. Rationale: 70+ competitions need a stable axis for joins.

- **Update cadence: manual replace.** When a fresh zip arrives (quarterly per the dataset's update pattern), drop it at `data/raw/opta-europa/<NEW_DATE>/europa.zip`, point `latest/` at the new date, re-run the wrangler. No incremental detection — full rebuild every time. Rationale: rebuilds take minutes (already verified at the file-size scale) and the zip ships infrequently.

## Open Questions

### Resolved during planning

- **Should we extract the zip in full?** No. Stream-read members. (Confirmed by disk math: 296 GB > 223 GB free.)
- **Where does player position come from when Understat doesn't have it?** Opta's `squad.json` per (team, season) lists every player with `position`. This plugs the 692-of-1275 squad position gap from the original audit observation.
- **Should non-WC2026-relevant nations / leagues be included in derived parquets?** Yes. The dataset is the dataset; downstream consumers filter. The model-input filter is a join, not a wrangler-level exclusion.
- **What about competitions where this data overlaps with Understat (e.g. EPL 2024-25)?** Both sources land in their own parquet; consumers join. Understat wins for xG; Opta wins for cup/Europe coverage.

### Deferred to implementation

- Cyrillic / Greek / Turkish player-name reconciliation: defer to a Phase-2 unit if the first crosswalk run leaves > 5% of WC2026 players unresolved.
- Whether to also extract the per-match `partidos/` JSONs that exist for some FA Cup/non-league entries — examined those would inflate scope; defer until model code asks for them.
- Choice of fuzzy-match library for the crosswalk (rapidfuzz vs jellyfish vs custom). Decide during Unit G with both libraries side-by-side on a 100-player sample.

## High-Level Technical Design

> *Directional, not implementation specification.*

```
~/Downloads/europa.zip
        │ (move once, no copy)
        ▼
data/raw/opta-europa/<YYYY-MM-DD>/europa.zip
        │
        │ tools/_opta_zip.py     ← stream-read members; never decompress to disk
        │
        ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  tools/build_opta_derived.py  (orchestrator)                 │
        │                                                              │
        │  1. opta_manifest.parquet         (file listing)             │
        │  2. opta_match.parquet            (one row per match)        │
        │  3. opta_match_event.parquet      (goals/cards/subs/VAR)     │
        │  4. opta_team_season.parquet      (team season aggregates)   │
        │  5. opta_player_season.parquet    (player season aggregates) │
        │  6. opta_player_match.parquet     (per-player appearances)   │
        │  7. player_id_crosswalk.parquet   (Opta ↔ Understat ↔ WC26)  │
        └──────────────────────────────────────────────────────────────┘
        │
        ▼
   downstream models  (Dixon-Coles, ensemble, last-N-matches view)
```

Join shape for the "last N matches per player" feature (combines this plan with the existing data-capture plan):

```
player_last_n_matches.parquet
  ←  club_player_match_xg.parquet            (Understat: full xG, league only)
  ←  opta_player_match.parquet               (Opta: minutes/goals/cards, every competition)
  ←  player_id_crosswalk.parquet             (joins the two via Understat ID and Opta ID)
  ←  wc2026_squads.parquet                   (filters to WC26 players)
```

## Implementation Units

- [ ] **Unit 1: Zip relocation and manifest**

**Goal:** Move the zip into the repo's gitignored raw tree and produce `data/derived/opta_manifest.parquet` listing every file in it.

**Requirements:** R1, R3, R6.

**Dependencies:** None.

**Files:**
- Create: `tools/_opta_zip.py` — utilities `open_zip()`, `read_member(path)`, `iter_members(filter_fn)`, all backed by a module-level cached `ZipFile` handle
- Create: `tools/build_opta_manifest.py`
- Create: `data/raw/opta-europa/<YYYY-MM-DD>/europa.zip` (moved from `~/Downloads/`)
- Create: `data/raw/opta-europa/latest/europa.zip` (mirror via symlink or copy)
- Create: `data/derived/opta_manifest.parquet`
- Test: `tools/test_opta_manifest.py`

**Approach:**
- Move the zip with `mv` (instant on same disk).
- Walk every `ZipInfo` in the archive; emit one row per file with parsed (competition, season, team, file_kind, byte_size, member_path).
- File-kind taxonomy: `matches_equipo`, `seasonstats`, `squad`, `team_csv`, `players_csv`, `seasonstats_csv`, `availability_csv`, `other`.
- Output sort: `(competition, season, team, file_kind)` for deterministic builds.

**Test scenarios:**
- Happy path — manifest contains 334,000+ rows; `competition` column has at least 70 distinct values.
- Edge case — `.ipynb_checkpoints/` files surface with `file_kind='other'` (not silently dropped).
- Edge case — non-ASCII team names round-trip cleanly (Türkiye, Bratislava, Linz, etc.).
- Determinism — running twice on the same zip produces a byte-identical parquet.

**Verification:**
- `data/derived/opta_manifest.parquet` exists with > 300,000 rows.
- Sample query: `opta_manifest.query("competition=='UEFA_UEFA_Champions_League' and season=='2024-2025'").shape` returns > 50 rows.

---

- [ ] **Unit 2: `opta_match.parquet` — one row per match**

**Goal:** Flatten every match across every competition and season into one denormalized parquet of match identities and final scores.

**Requirements:** R4, R6.

**Dependencies:** Unit 1.

**Files:**
- Create: `tools/_opta_match.py`
- Create: `data/derived/opta_match.parquet`
- Test: `tools/test_opta_match.py`

**Approach:**
- For each `matches_equipo.json` in the manifest, parse the embedded `match[]` array.
- Each match dedups: the same fixture appears in both contestants' files; pick one canonical record using `matchInfo.id` deduplication.
- Output schema: `match_id, competition, competition_kind, season, week, match_status, date, time_utc, local_date, home_team, home_team_id, away_team, away_team_id, ht_home, ht_away, ft_home, ft_away, winner, match_length_min, attendance, venue, source`
- Idempotent: sort `(date, match_id)`, dedupe on `match_id`.

**Patterns to follow:**
- Mirror `tools/pull_statsbomb.py:extract_team_xg` — flatten one nested JSON into N flat rows.

**Test scenarios:**
- Happy path — > 50,000 unique matches across 70+ competitions and 18 seasons.
- Edge case — A scheduled future fixture with `matchStatus='Fixture'` appears with null scores, not zero.
- Edge case — A match that was abandoned mid-game has `match_status='Abandoned'` and `match_length_min` reflects what was played.
- Integration — `match_id` joins cleanly to `opta_match_event.parquet` from Unit 3.

**Verification:**
- `opta_match.parquet` has the documented schema and row count > 50,000.
- Spot-check: Manchester United vs Arsenal 2025-03-09 appears with `ft_home=1, ft_away=1, winner='draw'`.

---

- [ ] **Unit 3: `opta_match_event.parquet` — one row per discrete event**

**Goal:** Flatten goals, cards, substitutions, and VAR decisions across every match into a single long-format event table.

**Requirements:** R4, R6.

**Dependencies:** Unit 2.

**Files:**
- Create: `tools/_opta_match_event.py`
- Create: `data/derived/opta_match_event.parquet`
- Test: `tools/test_opta_match_event.py`

**Approach:**
- For each match in `opta_match.parquet`, read its source `matches_equipo.json` member; iterate `liveData.goal`, `liveData.card`, `liveData.substitute`, `liveData.VAR`.
- One canonical schema covers all event types via nullable columns:
  `match_id, event_type, period_id, time_min, time_min_sec, timestamp, contestant_id, player_id, player_name, scorer_id, scorer_name, assist_player_id, assist_player_name, player_on_id, player_off_id, card_type, card_reason, var_decision, home_score_after, away_score_after, source`
- `event_type ∈ {goal, card, substitute, var}`.
- Idempotent: sort `(match_id, time_min, time_min_sec, event_type)`.

**Test scenarios:**
- Happy path — Goals + cards + subs sum across the dataset to > 1 million events.
- Edge case — A match with VAR decisions surfaces them with `event_type='var'` and `var_decision` populated.
- Edge case — A second-yellow card (`card_type='2YC'`) is preserved as its own event, not collapsed into the first yellow.
- Integration — Joining `opta_match` to `opta_match_event` on `match_id` produces correct goal counts vs `ft_home + ft_away`.

**Verification:**
- For a sample of 100 matches, `count(event_type='goal') == ft_home + ft_away` for the match.
- Spot-check: Manchester United vs Arsenal 2025-03-09 has 2 `goal` events with the expected scorers and assist.

---

- [ ] **Unit 4: `opta_team_season.parquet` — team season aggregates**

**Goal:** One row per (team, competition, season) carrying all 105 aggregate team stats.

**Requirements:** R4, R6.

**Dependencies:** Unit 1.

**Files:**
- Create: `tools/_opta_team_season.py`
- Create: `tools/_opta_competitions.py` (competition-kind taxonomy)
- Create: `data/derived/opta_team_season.parquet`
- Test: `tools/test_opta_team_season.py`

**Approach:**
- For each `seasonstats.json`, extract `contestant.stat[]` → flatten into one row.
- Column-rename rule: snake-case, strip parentheticals, collapse repeated underscores. Examples: `Goals from Inside Box` → `goals_from_inside_box`, `Shots On Target ( inc goals )` → `shots_on_target_inc_goals`. Mapping table written to `methodology/_opta-ingestion/column_map.csv`.
- All 105 stats kept; missing stats for some leagues come through as NaN.
- Output schema: `team, team_id, competition, competition_kind, country, season, games_played, goals, goals_conceded, total_shots, shots_on_target_inc_goals, possession_percentage, passing_accuracy, key_passes_attempt_assists, ... [101 more], source`
- Idempotent: sort `(competition, season, team)`.

**Patterns to follow:**
- Same column-name normalization as `tools/build_squad_xg_ratings.py:simplify_name`, just for stat names instead of player names.

**Test scenarios:**
- Happy path — > 50,000 rows across all (team, competition, season) combinations.
- Edge case — Arsenal 2024-25 EPL row has `goals=69, goals_conceded=34, possession_percentage=56.9`.
- Edge case — A small-league team-season with fewer than 105 stats reported has NaN for the missing ones, not zero.
- Integration — `team_id` matches the contestant IDs in `opta_match.parquet`.

**Verification:**
- Arsenal 2024-25 EPL row matches the values documented in this plan's Context section.
- For any (team, competition, season) where games_played=0, the row is still emitted with NaN aggregates — no silent drop.

---

- [ ] **Unit 5: `opta_player_season.parquet` — player season aggregates**

**Goal:** One row per (player, team, competition, season) with all ~120 aggregate player stats and identity columns.

**Requirements:** R4, R6.

**Dependencies:** Unit 1.

**Files:**
- Create: `tools/_opta_player_season.py`
- Create: `data/derived/opta_player_season.parquet`
- Test: `tools/test_opta_player_season.py`

**Approach:**
- For each `seasonstats.json`, extract `player[]` array. Each player row carries identity (`id, position, shirtNumber, firstName, lastName, shortFirstName, shortLastName, matchName`) plus their stat list (~11 to ~120 stats depending on minutes played).
- Same column normalization as Unit 4.
- Output schema: identity columns + all stat columns + `(team, team_id, competition, competition_kind, season, country, source)`.
- Idempotent: sort `(competition, season, team, player_id)`.

**Test scenarios:**
- Happy path — Top scorer across the EPL 2024-25 has the expected goal count.
- Edge case — A player who appeared in 1 match has 1-3 non-null stat fields and many NaNs; not dropped.
- Edge case — A player on multiple teams in one season (loan, transfer mid-year) appears in two rows, one per (team, season).
- Integration — `player_id` joins to `opta_player_match.parquet` from Unit 6.

**Verification:**
- Kai Havertz, Arsenal, EPL 2024-25 row has `goals=9, total_shots=44, key_passes_attempt_assists=14, time_played=1874`.

---

- [ ] **Unit 6: `opta_player_match.parquet` — player appearances and per-match contributions**

**Goal:** One row per (player, match) for every player who appeared. Carries minutes played, goals, assists, cards, derived from event stream + squad list.

**Requirements:** R4, R6.

**Dependencies:** Units 2, 3, 5.

**Files:**
- Create: `tools/_opta_player_match.py`
- Create: `data/derived/opta_player_match.parquet`
- Test: `tools/test_opta_player_match.py`

**Approach:**
- For each match: read its squad rosters (both teams from their respective `squad.json`).
- A player **appeared** if any of: a goal/card/substitute event references their `player_id`, OR they're in the starting XI per `squad.json`'s lineup field.
- Minutes-played derivation rule:
  - Started, never subbed off → `match_length_min`
  - Started, subbed off at minute X → `X`
  - Subbed on at minute Y, never subbed off → `match_length_min - Y`
  - Subbed on at minute Y, then off at minute Z → `Z - Y`
  - In squad but no appearance event and not in starting XI → not in this file
- Per-player aggregates derived from `opta_match_event`: goal_count, assist_count, yellow_card_count, red_card_count.
- Output schema: `match_id, date, competition, competition_kind, season, team, team_id, player_id, player, position, dorsal, minutes_played, started, goals, assists, yellow_cards, red_cards, source`.
- Idempotent: sort `(player_id, date, match_id)`.

**Patterns to follow:**
- Combine the event-stream pattern from Unit 3 with the roster pattern from Unit 5.

**Test scenarios:**
- Happy path — Kai Havertz's 2024-25 EPL appearances sum to ≈1,874 minutes (matches season aggregate from Unit 5).
- Edge case — A player subbed on at 90+5 has `minutes_played` near zero, not negative.
- Edge case — A starter sent off at minute 30 has `minutes_played=30, red_cards=1`.
- Edge case — A goal scored by a substitute has the goal credited to them in the per-match parquet.
- Integration — Sum of `goals` across all matches per (player, season) equals the season aggregate in Unit 5 for top scorers.

**Verification:**
- For 100 sampled players across 5 leagues, season totals from this file match Unit 5's season aggregates within 1 goal (rounding tolerance for own-goal edge cases).
- File row count > 1.5 million.

---

- [ ] **Unit 7: Player ID crosswalk**

**Goal:** `data/derived/player_id_crosswalk.parquet` resolving every WC2026 player to (Opta player_id, Understat player_id) where each exists.

**Requirements:** R5, R6.

**Dependencies:** Units 5, 6, plus the existing `data/derived/wc2026_squads.parquet` (when populated by the data-capture plan's Unit 2) and `data/derived/understat_player_xg.parquet`.

**Files:**
- Create: `tools/build_player_id_crosswalk.py`
- Create: `data/derived/player_id_crosswalk.parquet`
- Test: `tools/test_player_id_crosswalk.py`

**Approach:**
- Source identities: `wc2026_squads.parquet` (player + nation + club), Opta `opta_player_season.parquet` filtered to recent seasons (player_id + name + club + country), Understat `understat_player_xg.parquet` (player_id + name + last_team).
- Two-pass match per WC2026 player:
  1. Exact `simplify_name` match within the same club + country + recent season.
  2. Fuzzy-name match via `rapidfuzz.token_sort_ratio ≥ 85` within the same club.
- Output schema: `wc2026_player, nation, club_listed, opta_player_id, opta_name, opta_match_score, understat_player_id, understat_name, understat_match_score, resolved_via, notes`.
- Unresolved players get rows with NaN IDs and `notes` describing the failure mode.

**Patterns to follow:**
- Reuse `simplify_name` from `tools/build_squad_xg_ratings.py` (extract to `tools/_names.py` if not already done by the data-capture plan).

**Test scenarios:**
- Happy path — Kai Havertz resolves to both Opta and Understat IDs.
- Edge case — A WC26 player whose listed club is not in any Opta season appears with `opta_player_id=NaN` and `notes='club_not_in_opta'`.
- Edge case — Two players with the same simplified name on the same club resolve to the higher-fuzzy-score match, with both candidates logged.
- Integration — At least 95% of WC26 players whose listed league is one of EPL/La Liga/Bundesliga/Serie A/Ligue 1 resolve to an Opta ID.

**Verification:**
- Resolution rate ≥ 95% for top-5-league WC26 players.
- Resolution rate for non-Understat-league players (Liga MX, MLS, etc.) — these players still resolve to Opta if their league is in the dataset (Brasileirão not in this dataset, so still gap).

---

- [ ] **Unit 8: Wire into `weekly_pull.py` and freshness validator**

**Goal:** A single `python3 tools/weekly_pull.py` invocation re-derives all Opta parquets when a new zip is dropped in `data/raw/opta-europa/<date>/`. Freshness validator extends to cover the new files.

**Requirements:** R7, R8.

**Dependencies:** Units 1–7. The freshness-validator changes coordinate with the data-capture plan's Unit 6.

**Files:**
- Modify: `tools/weekly_pull.py`
- Modify: `tools/check_data_freshness.py` (extend with Opta file checks; this file is created by the data-capture plan's Unit 6)
- Modify: `tools/build_opta_derived.py` (orchestrator that runs Units 1–7 in order)

**Approach:**
- `tools/build_opta_derived.py` runs Unit 1 → Unit 4/5 in parallel → Unit 2 → Unit 3 → Unit 6 → Unit 7. Each step is skipped if its output is newer than the zip's mtime.
- Freshness rules: `OPTA_MAX_AGE_DAYS = 120` (quarterly cadence). `opta_match`, `opta_player_match` checked against the most recent match date in the file (must be within 30 days of the zip's mtime).
- `weekly_pull.py` adds one wrapped call to the orchestrator. Failure of the Opta build does not abort other pulls.

**Test scenarios:**
- Happy path — Drop a new zip, `python3 tools/weekly_pull.py` re-builds all Opta parquets in a single run.
- Edge case — Zip missing entirely; orchestrator logs a clear message and the rest of `weekly_pull.py` continues.
- Edge case — Re-running with no zip change is a no-op (every step skipped); total runtime under 10 seconds.
- Edge case — Stale zip (> 120 days); freshness validator exits 1 with a message naming the zip's mtime.

**Verification:**
- A clean rebuild from cold cache completes in under 30 minutes on the workstation (target; refine after first run).
- Cached re-run completes in under 10 seconds.

---

- [ ] **Unit 9: Model integration — Dixon-Coles priors and last-N-matches join**

**Goal:** Make Opta data visible to the existing models by (a) feeding Opta team-season aggregates as priors into the Dixon-Coles fit and (b) extending the unified `player_last_n_matches.parquet` (built by the data-capture plan's Unit 4c) with rows from `opta_player_match.parquet`.

**Requirements:** R9.

**Dependencies:** Units 6, 7, 8. The data-capture plan's Unit 4c. The existing `compound-model` Dixon-Coles code.

**Files:**
- Modify: `tools/build_player_last_n_matches.py` (created in the data-capture plan's Unit 4c) — read Opta rows in addition to Understat, set `xg_available` per row.
- Modify: `compound-model/<dixon-coles-script>` — read Opta team-season aggregates and use them as priors where the existing fit currently uses defaults.
- Modify: `methodology/<existing-models>/MODEL.md` files — add an entry under "Subjective adjustments" naming this dataset and its license constraint.

**Approach:**
- For the last-N-matches view: union Understat per-match (xG-bearing) rows and Opta per-match (no-xG) rows, deduplicate by `(player, date, opponent)` preferring Understat where both exist, sort by date desc, take the top N (default 5) per player.
- For Dixon-Coles: where the existing fit uses uniform priors per team, switch to a prior whose mean is set from Opta's `goals/games_played` and `goals_conceded/games_played` for that team's most recent season in `opta_team_season.parquet`. Strength of prior tunable; default 270 minutes equivalent (consistent with project shrinkage convention).
- Both changes gated behind a feature flag (`--use-opta` or env var) so the existing pipeline behaviour is preserved as default until the new path is validated.

**Test scenarios:**
- Happy path — Building `player_last_n_matches.parquet` with Opta available adds rows for UCL and cup matches; rows have `xg_available=False` for those.
- Edge case — A player with 5 league matches in Understat plus 2 UCL matches in Opta gets all 7 considered; the most-recent 5 are kept.
- Edge case — `--use-opta` flag off → output is byte-identical to the pre-Opta output (regression check).
- Integration — Dixon-Coles backtest log-loss does not regress more than 0.01 vs the no-Opta baseline; if it does, the regression is documented.

**Verification:**
- Backtest WC2022: log-loss within 0.01 of the existing baseline (or improved).
- For 10 sampled WC26 players, the last-5-matches output now includes a UCL or cup match where it didn't before.

---

- [ ] **Unit 10: Documentation**

**Goal:** Future contributors understand what Opta data is in `data/derived/`, where it came from, what its license constraints are, and how to refresh it.

**Requirements:** R10.

**Dependencies:** Units 1–9.

**Files:**
- Create: `methodology/_opta-ingestion/README.md` — schema, source provenance, license, refresh runbook
- Create: `methodology/_opta-ingestion/column_map.csv` — Opta original stat name → snake_case column name (~225 entries)
- Modify: `DEVELOPMENT.md` — add Opta to the data-flow section
- Create: `docs/solutions/raw/2026-05-07-opta-europa-ingestion.md` — captures the design (zip-as-source-of-truth, no full extraction) as a pattern to reuse for future big-data sources

**Test scenarios:**
- *Test expectation: none — documentation update.*

**Verification:**
- A new contributor reading `DEVELOPMENT.md` learns Opta exists, sees the pointers to the methodology folder, and can find the runbook to refresh.

## System-Wide Impact

- **Interaction graph:** New raw source + 7 new derived parquets. Wires into existing `weekly_pull.py` orchestrator and the freshness validator. Modifies the last-N-matches builder from the data-capture plan and (gated) the Dixon-Coles fit.
- **Error propagation:** Zip-read failures are loud and abort the Opta build only — never the rest of the pipeline. JSON parse failures inside individual files are logged and the row skipped (with a counter), not fatal.
- **State lifecycle risks:** No persistent state. Wrangler is pure read-from-zip → write-parquet. Re-running on the same zip is byte-identical. New zip → new derived parquets.
- **API surface parity:** New parquets are additive. Existing models continue working unchanged. The `--use-opta` feature flag controls whether new data influences existing model outputs.
- **Integration coverage:** The Unit 9 backtest comparison is the load-bearing integration check. Unit 6's row-count vs Unit 5's aggregate cross-check is a within-source sanity gate.
- **Unchanged invariants:** The 8-column predictions schema. The Understat / StatsBomb / martj42 pipelines. The Kalshi / Polymarket market-comparison logic. The existing Dixon-Coles model behaviour when `--use-opta` is off.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Streaming reads from a 20 GB zip are slower than expected | First-run timing measurement gates the design; if a run takes > 60 minutes we add per-table caching of intermediate parsed JSON to `data/derived/_opta_cache/` (gitignored) |
| Opta's column-name format drifts between the current zip and a future refresh | Column-map CSV is generated by the wrangler each run with a diff-able sort order; refresh-time drift is visible in PR review |
| WC26 players in non-Opta-covered leagues (Brasileirão, MLS, Liga MX, Saudi Pro) remain coverage gaps | This is honest: those players appear in the existing `club_xg_coverage_gaps.parquet` (data-capture plan) with reason `not_in_opta_either`; downstream models route around them |
| License risk if data is accidentally committed | `data/raw/opta-europa/` falls under the existing `data/raw/` gitignore; CI smoke check (separate plan) can grep for any `.json` from the dataset in tracked files and fail the PR |
| Player ID crosswalk has < 95% resolution rate | Phase-2 unit (deferred) for Cyrillic/Greek/Turkish handling and within-team fuzzy match; for first version, accept gaps and document them |
| Dixon-Coles regression > 0.01 log-loss when `--use-opta` flips on | Unit 9 explicitly checks; flag stays default-off until investigated; may indicate Opta-derived priors are too loose vs current uniform priors |
| Zip refresh frequency unknown | First refresh proves the cadence; document in methodology README and revisit |

## Documentation / Operational Notes

- Methodology folder lives at `methodology/_opta-ingestion/`. Mirrors the convention from the data-cleanse plan note (per-task, leading-underscore-namespace for non-model methodology).
- License callout in MODEL.md for any model that reads Opta-derived parquets — must name "Opta basic stats feed via scoresway.com export, license-restricted, not redistributable".
- Refresh runbook (≤ 10 steps) in `methodology/_opta-ingestion/README.md`: drop zip → mv to dated raw dir → repoint `latest/` → `python3 tools/build_opta_derived.py` → freshness validator green.

## Sources & References

- Data source: `~/Downloads/europa.zip` (will move to `data/raw/opta-europa/2026-05-07/europa.zip`)
- Original provenance: scraped from `https://www.scoresway.com/`, format is Opta basic stats feed
- Existing pipeline: `tools/pull_statsbomb.py` (extraction pattern), `tools/build_squad_xg_ratings.py` (name-normalization pattern), `tools/weekly_pull.py` (orchestrator)
- Sibling plan: `docs/plans/2026-05-06-001-fix-data-cleanse-games-teams-players-plan.md` (Understat per-match, last-N-matches deliverable)
- Project standards: `DEVELOPMENT.md` (Data contributor track, Reproducibility standard, Subjectivity and bias policy)
