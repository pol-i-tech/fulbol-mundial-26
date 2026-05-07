---
title: "feat: Capture recent games and announced WC2026 squads"
type: feat
status: active
date: 2026-05-07
---

# feat: Capture recent games and announced WC2026 squads

## Overview

Models read from `data/derived/`, but three upstream gaps mean models are training on stale or missing inputs:

1. The international-match record stops at Copa America 2024 (July 2024). Roughly ten months of international football — UEFA Nations League 2024-25, FIFA WC qualifying windows (Sep/Oct/Nov 2024, March/June/Sep/Oct/Nov 2025, March 2026), and pre-tournament friendlies — never reach `data/derived/`.
2. `data/raw/squads/wc2026_squads_raw.json` is an empty array. The Wikipedia squad scrape is not producing rows, so `data/derived/wc2026_squads.parquet` is built from an empty source. WC2026 squad announcements are happening now (tournament starts 2026-06-11).
3. Club form data exists only as **season aggregates** (`data/derived/understat_player_xg.parquet`). For each WC2026 player, models cannot see *per-match* xG/xGA at the club level — needed both for recency-weighted form features and for evaluating performance against UCL-quality opposition vs domestic-league opposition.

This plan adds new pulls plus a validation step so the most recent games, announced players, and club-level per-match xG/xGA land in `data/derived/` cleanly, dated, and idempotently — ready for downstream models. Cleaning means: schema conformance, deduplication, name normalization, and a freshness check that fails loudly. It does **not** mean re-deriving xG, fitting models, or correcting historical bias — those are separate concerns.

## Problem Frame

A data engineer's job here is to deliver fresh, schema-correct inputs to the modeling layer. Today the pipeline produces correct outputs from stale inputs. Concretely:

- `data/derived/statsbomb_team_xg.parquet` covers WC2018, Euro2020, WC2022, Euro2024, Copa2024 — nothing past 2024-07-14. StatsBomb open-data does not publish UEFA Nations League or WC qualifiers, so a non-StatsBomb source is required for recency.
- `data/derived/wc2026_squads.parquet` is empty (built from `[]`). Models that should read from announced rosters fall back to whatever proxy they have (likely the most recent tournament squads), which is exactly the bias this pipeline was built to avoid.
- `data/raw/martj42/2026-04-28/` exists, suggesting `martj42/international_results` is already pulled, but no derived match-level table is produced for downstream consumers — the file is read inline by `weekly_pull.py` for Elo and never persisted in cleansed form.
- `tools/pull_fbref_national.py` exists but FBref is hard-blocked by Cloudflare (`DEVELOPMENT.md`). Treat that file as unusable for this plan.
- `tools/pull_understat_players.py` pulls **season aggregates** from Understat (one row per player per season) — not per-match. The same Understat client (`understat` Python package) exposes `get_team_results(team, season)` and `get_player_matches(player_id)` which give per-match xG/xGA at team and player level, but neither is wired up.

### Coverage reality for club xG/xGA, UCL, and domestic cups

Verified directly against the live APIs and HTML on 2026-05-07 — what's reachable, what isn't:

| Source | League coverage | Per-match xG | UCL xG | Domestic cup xG |
|---|---|---|---|---|
| Understat (`get_team_results`, `get_player_matches`) | EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL | Yes | **No** — verified: Real Madrid 2024 returns exactly 38 rows (one La Liga season). Player page HTML contains zero "tournament / champions / UCL / Europa / cup" mentions. Understat is strictly league-only. | **No** — same reason |
| StatsBomb open-data | National-team tournaments only | n/a | No | No |
| FBref | Nominally everything | Cloudflare-blocked — unusable | Same | Same |
| Sofascore / Whoscored / Fotmob | Nominally everything | Anti-bot + license-restrictive — out of scope | Same | Same |
| football-data.org (free tier) | UCL, top European leagues | n/a (results + fixtures only, no xG) | Match list + scores, no xG | Match list + scores, no xG |
| Wikipedia season pages | Everything that has a Wikipedia page | n/a (no xG) | Match list + scores by season, no xG | Match list + scores, no xG |

**Practical implication for "last N games per player"**:
- For a player in one of the six Understat leagues, we get the last N **league** matches with full xG/xA/shots/key_passes.
- For UCL and domestic cup matches that same player participated in, **we cannot get xG license-clean today**. We can list the fixtures (date, opponent, result) from football-data.org or Wikipedia and tag them `xg_available=false`.
- For players whose club is in a non-Understat league (Liga MX, MLS, Saudi Pro, Brasileirão, Eredivisie, Primeira Liga, Argentine Primera, etc.), we get nothing — they go to `club_xg_coverage_gaps.parquet`.

Downstream models then have three signal tiers per player: full-xG league matches, fixture-only UCL/cup appearances, and explicit gaps. That is honest about what's actually in the data.

## Requirements Trace

- R1. `data/derived/recent_internationals.parquet` exists and contains every full international match from 2024-08-01 through the most recent international break, in a documented schema (date, home, away, home_goals, away_goals, competition, source).
- R2. `data/derived/wc2026_squads.parquet` is non-empty and contains player rows for every nation listed on the Wikipedia squads page, with `nation`, `player`, `position`, `club`, and `is_final_squad` boolean.
- R3. Both pulls are idempotent: re-running on the same day produces the same outputs; running on a later day adds new matches and updates squad announcements without duplicating prior rows.
- R4. Both pulls write date-stamped raw snapshots to `data/raw/<source>/<YYYY-MM-DD>/` and the most recent snapshot to a `latest/` symlink-equivalent (matches existing `martj42` pattern).
- R5. A freshness validator fails loudly when either derived parquet is older than a configured threshold (matches stale > 14 days; squads stale > 7 days during May/June 2026).
- R6. The new pulls plug into `tools/weekly_pull.py` so a single `python3 tools/weekly_pull.py` produces refreshed inputs.
- R7. `data/derived/club_team_match_xg.parquet` exists — one row per (team, season, match) for every club currently fielding a WC2026 player in the top 5 European leagues + RFPL, with team xG, xGA, opponent, date, competition (league or cup), home/away.
- R8. `data/derived/club_player_match_xg.parquet` exists — one row per (player, match) for every WC2026 player on a club covered by Understat, **league matches only**. Schema includes player_id, player, team, opponent, date, competition (always one of the six leagues), minutes, xg, xa, key_passes, shots, position.
- R9. `data/derived/player_last_n_matches.parquet` exists — for every WC2026 player, the most recent N matches (default N=5) across **all** competitions the data sources can see, with explicit competition labels. League matches carry full xG/xA from Understat; UCL and domestic-cup matches carry fixture data only (date, opponent, result, minutes) with `xg_available=false`. This is the single deliverable downstream form-recency features should join on.
- R10. The known-gap list (clubs in non-Understat leagues, players whose Understat ID does not resolve, UCL/cup matches lacking xG) is written to `data/derived/club_xg_coverage_gaps.parquet` so downstream models can detect and route around missing rows rather than silently using stale/zero data.

## Scope Boundaries

- **Not** computing xG for the recent matches. xG requires shot-level event data (StatsBomb-quality), which `martj42` does not provide. Recent games come in goal-only.
- **Not** changing any model code. Models continue reading the existing parquet schemas; the new files are *additive*.
- **Not** auditing or correcting existing data (the prior version of this plan covered that — it was out of scope for "data engineer captures recent data").
- **Not** building shrinkage priors, manual override layers, or audit reports. Those are separate plans if they're needed.
- **Not** pulling FBref. Hard-blocked.
- **Not** computing xG ourselves for any source that lacks it. Recent international matches and non-Understat-league clubs come in as known coverage gaps.
- **Not** producing xG values for UCL or domestic cup matches. No license-clean source provides them today (verified). UCL/cup matches are captured as fixtures only with `xg_available=false`.
- **Not** scraping Sofascore / Whoscored / Fotmob / Stats Perform. Anti-bot and license issues out of scope.
- **Not** building a homegrown xG model to fill UCL/cup gaps. Separate, much larger effort.

### Deferred to Separate Tasks

- Adding xG to recent international matches (would need a StatsBomb licensed feed, an Opta-backed source, or a homegrown xG model — all out of scope here).
- Backfilling shot-level data for Nations League / WCQ.
- Whatever model refit is appropriate after fresh data lands.

## Context & Research

### Relevant Code and Patterns

- `tools/pull_wc2026_squads.py` — already exists, fetches `https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads`, caches HTML, parses tables. Currently producing empty JSON — root-cause investigation is part of Unit 2.
- `data/raw/squads/squads_wiki_raw.html` — cached HTML exists; the parse step is what's failing.
- `tools/weekly_pull.py` — orchestrator. Reads `martj42/international_results` for Elo computation. Uses `NAME_TO_FIFA3` and `ISO2_TO_FIFA3` dicts as the canonical name mapping; reuse rather than duplicate.
- `data/raw/martj42/latest/` — existing snapshot pattern (date folder + `latest/` mirror). Match this for consistency.
- `tools/pull_statsbomb.py` — pattern for paginated, cached, idempotent pulls.
- `DEVELOPMENT.md` — "Data contributor" track explicitly defines: pull scripts in `tools/`, raw to `data/raw/<source>/<YYYY-MM-DD>/`, derived to `data/derived/`, must be idempotent, document source + cadence + rate limits in the script header.

### External References

- `martj42/international_results` — public GitHub CSV: `https://raw.githubusercontent.com/martj42/international_results/master/results.csv`. Goals only, not xG. Includes friendlies, qualifiers, all confederations. Update cadence: usually within 24h of match.
- Wikipedia WC2026 squads page: `https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads`. Final squads must be submitted to FIFA before the tournament; preliminary squads (35-player) are usually announced 2-3 weeks before final squads.

## Key Technical Decisions

- **Recent-games source = `martj42/international_results`.** Already in the pipeline, license-clean, goals-only is acceptable for an Elo/form input. Rationale: any richer source (FBref, paid Opta) costs more than it adds at this scope.
- **Two distinct derived files, one per source.** `recent_internationals.parquet` (matches) and `wc2026_squads.parquet` (rosters) are independent; one failing should not block the other. Keep them separate.
- **`is_final_squad` boolean rather than two parquet files.** Wikipedia's squads page distinguishes preliminary vs final via section headers. One file with a flag preserves history; consumers filter as needed.
- **Freshness check is a function, not a cron job.** `tools/check_data_freshness.py` callable both standalone and from `weekly_pull.py`. Returns nonzero on stale data. Rationale: orchestrator already exists, no new infra.
- **Idempotency via primary key on (date, home, away) for matches and (nation, player) for squads.** Re-pulls upsert by key; no duplicate rows possible. Matches the existing martj42 source-of-truth model.
- **`latest/` is a directory copy, not a symlink.** Cross-platform-portable for any contributor on Windows; matches what `data/raw/martj42/latest/` already does.
- **Per-match club xG comes from Understat via the `understat` Python client.** Already a project dependency. `get_team_results(team, season)` for team-level rows; `get_player_matches(player_id)` for player-level rows (which include UCL appearances). Rationale: zero new dependencies, zero new license risk, matches the existing pull style.
- **Two new derived files for club xG: team-level and player-level.** Both keyed at (match, team) and (match, player) respectively. Joinable via `match_id` so consumers can pivot either way. Rationale: avoids a wide-and-sparse single file; mirrors the existing `statsbomb_team_xg` / `statsbomb_player_xg` split for the national-team data.
- **Coverage gaps file is a first-class output, not a log line.** `data/derived/club_xg_coverage_gaps.parquet` lists every WC2026 player whose club is not in an Understat-covered league, with `player, nation, club, league_guess, reason`. Rationale: silent gaps cause silent model bias; explicit gaps let downstream code branch.

## Open Questions

### Resolved During Planning

- **Should we attempt to derive xG for recent matches?** No. Out of scope; goals-only is enough for Elo/form features. (If a future model needs xG for recent matches, that's a separate plan with a separate source decision.)
- **Where do final-squad rows come from when Wikipedia hasn't been updated yet?** Wikipedia's squads page tracks both preliminary (35-player) and final (26-player) lists; `is_final_squad` is False until Wikipedia flips them. Re-running the pull picks up the change.
- **Should non-WC2026 nations be included in `recent_internationals.parquet`?** Yes — the file mirrors `martj42` faithfully so it's reusable for non-WC contexts (Elo updates, form features). Consumers filter by FIFA3 code.

### Deferred to Implementation

- Why is `pull_wc2026_squads.py` currently producing `[]`? Root cause is unknown until Unit 2 runs; could be Wikipedia DOM change, BeautifulSoup selector drift, or an upstream redirect. Diagnosis happens in-unit.
- Exact freshness thresholds (14 days for matches; 7 days for squads in May/June 2026, 30 days otherwise) — these are starting values. Adjust in Unit 6 once the validator runs against real data.

## Implementation Units

- [ ] **Unit 1: Pull recent international matches from `martj42`**

**Goal:** Produce `data/derived/recent_internationals.parquet` containing every full international from 2024-08-01 to the run date, deduplicated and dated.

**Requirements:** R1, R3, R4.

**Dependencies:** None.

**Files:**
- Create: `tools/pull_recent_internationals.py`
- Create: `data/raw/martj42/<YYYY-MM-DD>/results.csv` (date-stamped snapshot)
- Create: `data/derived/recent_internationals.parquet`
- Test: `tools/test_pull_recent_internationals.py`

**Approach:**
- Download `https://raw.githubusercontent.com/martj42/international_results/master/results.csv` to `data/raw/martj42/<YYYY-MM-DD>/results.csv`. Mirror to `data/raw/martj42/latest/`.
- Filter `date >= 2024-08-01` (after Copa2024 final).
- Drop rows where `home_team` or `away_team` does not map to a FIFA3 code via the `NAME_TO_FIFA3` dict in `tools/weekly_pull.py`. Log dropped rows to stderr — do not fail.
- Output schema: `date, home, away, home_fifa3, away_fifa3, home_goals, away_goals, tournament, neutral, source`.
- Idempotency: write parquet with the full deduplicated table each run. Re-running on the same input produces a byte-identical file (sort by `(date, home, away)` before write).
- Document source URL, update cadence, and any rate limits in the script header per `DEVELOPMENT.md`.

**Patterns to follow:**
- Same date-folder + `latest/` snapshot pattern already used in `data/raw/martj42/`.
- Reuse `NAME_TO_FIFA3` from `tools/weekly_pull.py`; do not duplicate the dict.

**Test scenarios:**
- Happy path — Run on a fresh day; assert parquet has > 100 rows, contains a known recent match (e.g., a 2025 Nations League fixture).
- Edge case — A row with `home_team` outside `NAME_TO_FIFA3` is logged and skipped, not crashed.
- Edge case — Re-running on the same day produces a byte-identical parquet (deterministic sort).
- Integration — After running, `weekly_pull.py` can read `recent_internationals.parquet` without schema errors.

**Verification:**
- `data/derived/recent_internationals.parquet` exists, has the documented schema, and contains at least one match per international break since 2024-08-01.
- A second run on the same day produces the same file.

---

- [ ] **Unit 2: Fix the WC2026 squad pull**

**Goal:** `data/derived/wc2026_squads.parquet` becomes non-empty with one row per announced player per nation, including `is_final_squad` boolean.

**Requirements:** R2, R3, R4.

**Dependencies:** None.

**Files:**
- Modify: `tools/pull_wc2026_squads.py`
- Modify (if cached HTML is stale): `data/raw/squads/squads_wiki_raw.html`
- Create: `data/raw/squads/<YYYY-MM-DD>/wc2026_squads_raw.json` (replaces the static-path raw file)
- Modify: `data/derived/wc2026_squads.parquet`
- Test: `tools/test_pull_wc2026_squads.py`

**Approach:**
- Diagnose first. The cached HTML at `data/raw/squads/squads_wiki_raw.html` exists; the JSON output is `[]`. Likely causes: (a) Wikipedia DOM changed (table class or section headers), (b) BeautifulSoup selector mismatched, (c) an early `return` short-circuiting the loop. Re-fetch the page once with `?action=raw` disabled to confirm structure, then patch the parser.
- Output schema: `nation, player, position, club, shirt_number, is_final_squad, scraped_date, source_url`.
- `is_final_squad` derived from the section heading on the Wikipedia page ("Final squad" / "Provisional squad"). When ambiguous, default to False.
- Snapshot raw HTML and parsed JSON to `data/raw/squads/<YYYY-MM-DD>/`. Mirror to `data/raw/squads/latest/`.
- Idempotency: same key-deduped write pattern as Unit 1. Re-running upserts by `(nation, player)`.

**Patterns to follow:**
- Existing fetch-cache idiom in the script (already caches HTML).
- Same date-folder snapshot pattern as Unit 1.

**Test scenarios:**
- Happy path — Run; assert at least 30 nations and ≥ 600 players in output.
- Edge case — Wikipedia DOM-change defense: a small unit test runs the parser against a checked-in HTML fixture (`tests/fixtures/wc2026_squads_sample.html`) so future Wikipedia changes break the test, not silently the data.
- Edge case — A nation with only a "Provisional squad" section produces rows with `is_final_squad=False`; the same nation re-pulled after Wikipedia adds "Final squad" produces `is_final_squad=True` and updates the rows in place.

**Verification:**
- `data/derived/wc2026_squads.parquet` is non-empty and has ≥ 30 nations.
- `data/raw/squads/wc2026_squads_raw.json` (or its dated equivalent) is non-empty.

---

- [ ] **Unit 3: Pull per-match team xG/xGA for clubs of WC2026 players**

**Goal:** Produce `data/derived/club_team_match_xg.parquet` — one row per (team, season, match) for every club in the top 5 European leagues + RFPL that fields at least one WC2026 player.

**Requirements:** R7, R3, R4.

**Dependencies:** Unit 2 (needs the squad list to know which clubs to pull).

**Files:**
- Create: `tools/pull_club_team_match_xg.py`
- Create: `data/raw/understat/team_results/<league>_<season>/<team>.json`
- Create: `data/derived/club_team_match_xg.parquet`
- Test: `tools/test_pull_club_team_match_xg.py`

**Approach:**
- Read `data/derived/wc2026_squads.parquet`. Build the set of distinct clubs whose league matches one of `EPL, La_liga, Bundesliga, Serie_A, Ligue_1, RFPL`. (League is already in the squad row from the Wikipedia parse; if it isn't, derive from the Understat 2024-season player aggregates already in `data/derived/understat_player_xg.parquet`.)
- For each (team, season) in `[2023, 2024, 2025]` × that club set, call `understat.Understat.get_team_results(team, season)` via the existing client pattern in `tools/pull_understat_players.py`.
- Cache raw JSON per (team, season). Reuse on subsequent runs unless the file is older than 7 days, then refresh.
- Output schema: `match_id, team, season, date, opponent, is_home, competition, team_xg, team_xga, team_goals, opponent_goals, source`.
- `competition` is what Understat returns (typically `"league"`; UCL games are not surfaced here — they live in player-match data only). Keep the value as Understat reports it.
- Idempotent write sorted by `(team, season, date)`.

**Patterns to follow:**
- Async pattern from `tools/pull_understat_players.py`. Reuse `aiohttp.ClientSession` and the `understat` client.
- Cache-first idiom (already in `pull_league_season`).

**Test scenarios:**
- Happy path — Run on the post-Unit-2 squad list; assert at least 50 distinct teams and at least 1500 match rows across 3 seasons.
- Edge case — A team-season returns zero matches (e.g., a newly promoted team in 2023 with no Understat data); script skips with a logged warning, does not crash.
- Edge case — Re-running on the same day with cached files produces a byte-identical parquet.
- Integration — A known recent match (e.g., a Real Madrid La Liga game in March 2026) appears with team_xg, team_xga, and the correct opponent.

**Verification:**
- `data/derived/club_team_match_xg.parquet` is non-empty, has the documented schema, and contains seasons 2023, 2024, and 2025 for at least one club.

---

- [ ] **Unit 4: Pull per-match player xG/xA for WC2026 players (Understat leagues only)**

**Goal:** Produce `data/derived/club_player_match_xg.parquet` — one row per (player, league-match) for every WC2026 player whose Understat ID resolves. **League matches only**, since Understat does not surface UCL or domestic cup data (verified 2026-05-07: a player page returns league matches only with no `competition` field, and the page HTML contains zero "tournament/champions/UCL/Europa/cup" mentions).

**Requirements:** R8, R3, R4.

**Dependencies:** Unit 2 (squad list); Unit 3 (team listing reuse for player-ID resolution).

**Files:**
- Create: `tools/pull_club_player_match_xg.py`
- Create: `data/raw/understat/player_matches/<player_id>.json`
- Create: `data/derived/club_player_match_xg.parquet`
- Create: `data/derived/club_xg_coverage_gaps.parquet`
- Test: `tools/test_pull_club_player_match_xg.py`

**Approach:**
- Resolve each WC2026 player to an Understat `player_id`. Two-pass strategy:
  1. Fast path — join on the existing `data/derived/understat_player_xg.parquet` by normalized name (reuse `simplify_name()` from `tools/build_squad_xg_ratings.py`).
  2. Fallback — for unresolved players, call `understat.Understat.get_team_players(team, season)` for the player's listed club and fuzzy-match by name within that team only (much higher accuracy than league-wide fuzzy match).
- For each resolved player_id, call `understat.Understat.get_player_matches(player_id)`. The response has fields `goals, shots, xG, time, position, h_team, a_team, h_goals, a_goals, date, id, season, xA, assists, key_passes, npg, npxG, xGChain, xGBuildup` — confirmed from a 2026-05-07 probe. There is no competition tag; we infer the league by joining `(team, season, date)` against the team-results data from Unit 3 (which is also league-only).
- Output schema: `player_id, player, nation, team, season, date, opponent, is_home, competition, minutes, goals, xg, xa, key_passes, shots, position, source`. `competition` is the league name (one of EPL/La_liga/Bundesliga/Serie_A/Ligue_1/RFPL).
- Players with no Understat ID resolved are written to `data/derived/club_xg_coverage_gaps.parquet`: `player, nation, club, league_guess, reason` where `reason` is one of `not_in_understat_league`, `name_not_resolved`, `team_not_in_understat`.
- Idempotent: cache per-player JSON; refresh files older than 7 days; output sort `(player_id, season, date)`.

**Patterns to follow:**
- Async client pattern from Unit 3.
- Name normalization shared with the existing build script (extract `simplify_name` to `tools/_names.py` if not already done).

**Test scenarios:**
- Happy path — At least 80% of WC2026 players whose listed league is one of the six covered leagues resolve to an Understat ID.
- Happy path — A known league match for a covered player (e.g., Mbappé's recent Real Madrid La Liga matches) appears with full xG/xA/shots.
- Edge case — A player whose listed club is in Liga MX appears in `club_xg_coverage_gaps.parquet` with `reason=not_in_understat_league`, not in the main player file.
- Edge case — A player whose name doesn't resolve via either pass is logged to coverage gaps with `reason=name_not_resolved`, build continues.
- Integration — `club_team_match_xg` (Unit 3) and `club_player_match_xg` are joinable on `(team, date)` for cross-validation; counts of league matches per team-season match.

**Verification:**
- `data/derived/club_player_match_xg.parquet` is non-empty and contains league matches for resolved players across the 2024 and 2025 seasons.
- `data/derived/club_xg_coverage_gaps.parquet` exists and lists every player not represented in the main file, with a non-empty `reason`.

---

- [ ] **Unit 4b: Pull UCL and domestic-cup fixtures (no xG) for WC2026 players**

**Goal:** Produce `data/derived/club_player_cup_fixtures.parquet` — one row per (player, match) for UCL and domestic-cup matches a WC2026 player participated in, **fixtures only** (date, teams, score, competition). No xG, because no license-clean source provides it for these competitions today.

**Requirements:** R9.

**Dependencies:** Unit 2 (squad list).

**Files:**
- Create: `tools/pull_player_cup_fixtures.py`
- Create: `data/raw/cup_fixtures/<YYYY-MM-DD>/ucl_results.json`
- Create: `data/raw/cup_fixtures/<YYYY-MM-DD>/domestic_cup_results.json`
- Create: `data/derived/club_player_cup_fixtures.parquet`
- Test: `tools/test_pull_player_cup_fixtures.py`

**Approach:**
- Source: `football-data.org` free tier (10 competitions, 12 calls/min). Configure via `FOOTBALL_DATA_API_KEY` env var; document in script header.
- Pull team-level fixtures for: UCL (`CL`), FA Cup (`FAC`), Copa del Rey, DFB-Pokal, Coppa Italia, Coupe de France for the 2024-25 and 2025-26 seasons. Filter to teams that field a WC2026 player.
- Per-player participation is **not** in football-data.org's free tier. To assign a player to a match, look up the player's Understat `get_player_matches` response — any match dated within the cup match's window (±1 day) for the player's club that does NOT appear in `club_team_match_xg` (Unit 3, league-only) is inferred to be a cup or UCL appearance. Match by date + opponent.
- For matches we cannot tag confidently, write them to coverage gaps rather than guess.
- Output schema: `player_id, player, nation, team, season, date, opponent, is_home, competition, h_goals, a_goals, source, xg_available=False`.
- Idempotent: per-day raw snapshots; output sort `(player_id, date)`.
- Honest fallback: if `FOOTBALL_DATA_API_KEY` is missing, the script logs a warning, writes an empty file with the schema, and the rest of the pipeline still runs. The freshness validator surfaces the gap.

**Patterns to follow:**
- Same date-folder + `latest/` snapshot pattern as Unit 1.
- Token in env var, never in code (matches `DEVELOPMENT.md` "Environment Variables" section).

**Test scenarios:**
- Happy path — Run with API key; assert at least 30 UCL matches recorded for the 2024-25 season and at least one domestic cup match per major league.
- Edge case — API key missing; script logs warning, writes empty parquet with correct schema, exits 0.
- Edge case — A match in football-data.org cannot be matched to a player in Understat (e.g., player ID didn't resolve); recorded in coverage gaps with `reason=fixture_no_player_link`.
- Edge case — Same match appears in both UCL feed and domestic-cup feed (shouldn't happen, but defensive); deduplicated by `(date, h_team, a_team, competition)`.

**Verification:**
- `data/derived/club_player_cup_fixtures.parquet` exists, has the documented schema, and contains UCL fixtures for at least one covered season.
- Every row has `xg_available=False` so downstream consumers cannot accidentally use xG fields.

---

- [ ] **Unit 4c: Build the unified "last N matches per player" deliverable**

**Goal:** Produce `data/derived/player_last_n_matches.parquet` — for every WC2026 player, the most recent N matches across **all** competitions captured (default N=5). Combines Unit 4 (league with xG) + Unit 4b (UCL/cup without xG) into one form-recency view.

**Requirements:** R9.

**Dependencies:** Units 4 and 4b.

**Files:**
- Create: `tools/build_player_last_n_matches.py`
- Create: `data/derived/player_last_n_matches.parquet`
- Test: `tools/test_build_player_last_n_matches.py`

**Approach:**
- Read `club_player_match_xg.parquet` (league + xG) and `club_player_cup_fixtures.parquet` (UCL/cup, no xG).
- Concatenate; key on `player_id, date`.
- For each player, take the N most recent rows by `date` (default N=5, configurable via constant at top of script).
- Output schema: `player_id, player, nation, team, date, opponent, is_home, competition, competition_kind` (`league` | `ucl` | `domestic_cup`), `minutes, goals, xg, xa, shots, key_passes, xg_available, source`.
- Players with fewer than N total matches across all sources still get rows for what's available, plus a `gap_count = N - actual` annotation in `data/derived/club_xg_coverage_gaps.parquet`.
- Idempotent and deterministic — sort, no random ties.

**Patterns to follow:**
- Same parquet read-and-write idiom as `tools/build_squad_xg_ratings.py`.

**Test scenarios:**
- Happy path — A WC26 player on a covered club has 5 rows, mixing league (with xG) and UCL/cup (without xG); the rows are sorted by date descending.
- Edge case — A WC26 player on Liga MX has 0 rows in this file and appears in coverage gaps with `gap_count=5`.
- Edge case — A player with exactly 3 league matches and no UCL/cup appearances has 3 rows and `gap_count=2`.
- Edge case — Re-running on the same input produces a byte-identical parquet (deterministic sort).
- Integration — Joining this file against `wc2026_squads.parquet` covers ≥ 60% of WC26 players (the rest go to coverage gaps).

**Verification:**
- `data/derived/player_last_n_matches.parquet` is non-empty.
- Sum of `gap_count` for missing players matches the count in `club_xg_coverage_gaps.parquet`.
- A spot-checked WC26 player from a covered club shows expected recent fixtures.

---

- [ ] **Unit 5: Wire all pulls into `weekly_pull.py`**

**Goal:** A single `python3 tools/weekly_pull.py` invocation refreshes all six new parquets (recent internationals, squads, club team match xG, club player match xG, cup fixtures, last-N matches).

**Requirements:** R6.

**Dependencies:** Units 1, 2, 3, 4, 4b, 4c.

**Files:**
- Modify: `tools/weekly_pull.py`

**Approach:**
- Add the six pulls to the orchestrator's existing run sequence (matches the pattern already in place for Kalshi, Polymarket, Elo).
- Each pull is wrapped so a single source failure does not abort the whole run; failures are logged and surfaced at the end.
- Order matters: squad pull (Unit 2) runs before club xG pulls (Units 3, 4); cup-fixtures pull (Unit 4b) runs after Unit 4 since it joins against player-match data; the last-N builder (Unit 4c) runs last since it consumes Units 4 and 4b.
- No change to the existing comparison-table logic.

**Test scenarios:**
- Happy path — End-to-end `weekly_pull.py` run produces all six new parquets and the existing comparison table without errors.
- Edge case — Wikipedia is unreachable during the run; squad pull logs the failure, the dependent club-xG pulls skip with a logged message naming the dependency, match pull still completes, comparison table still builds from remaining inputs.
- Edge case — `FOOTBALL_DATA_API_KEY` is unset; cup-fixtures pull writes empty parquet, last-N builder still produces output (league-only for everyone), pipeline does not abort.

**Verification:**
- Running `python3 tools/weekly_pull.py 2026-05-07` from a clean tree produces all six new parquets.

---

- [ ] **Unit 6: Freshness validator**

**Goal:** A standalone check that fails loudly when derived data is stale, callable from `weekly_pull.py` and CI.

**Requirements:** R5.

**Dependencies:** Units 1, 2, 3, 4, 4b, 4c.

**Files:**
- Create: `tools/check_data_freshness.py`
- Modify: `tools/weekly_pull.py` (call the validator at end of run)
- Test: `tools/test_check_data_freshness.py`

**Approach:**
- Read all six derived parquets. Compute the most recent match date for `recent_internationals`, `club_team_match_xg`, `club_player_match_xg`, `club_player_cup_fixtures`, and `player_last_n_matches`; the most recent `scraped_date` for `wc2026_squads`.
- Configured thresholds (constants at top of file):
  - `MATCHES_MAX_AGE_DAYS = 14` (international and club matches, last-N file)
  - `SQUADS_MAX_AGE_DAYS_TOURNAMENT = 7`, `SQUADS_MAX_AGE_DAYS_DEFAULT = 30` (squad threshold tightens automatically between 2026-05-15 and 2026-07-15)
  - `CLUB_PLAYER_MATCH_MAX_AGE_DAYS = 14`
  - `CUP_FIXTURES_MAX_AGE_DAYS = 14`
- Exit code 0 = fresh, 1 = stale (with a printed reason naming each offending file and its age), 2 = file missing.
- No network calls; pure reads of the derived parquets.
- Cup-fixtures empty file (because API key missing) is reported as a *coverage warning*, not staleness — exit code 0 with a printed warning naming `FOOTBALL_DATA_API_KEY` as the unblocking action.

**Test scenarios:**
- Happy path — All six files current; exit 0.
- Edge case — Match file's most recent date is 20 days ago; exit 1, message names the offending file and age.
- Edge case — A derived file missing entirely; exit 2.
- Edge case — Today's date is during the tournament window (June 2026); squad-staleness threshold is 7 days, not 30.

**Verification:**
- The validator runs in under 5 seconds.
- A staged staleness scenario (artificially old parquet) produces a clear actionable error.

---

- [ ] **Unit 7: Document and ship**

**Goal:** Update docs so future contributors know what these new files contain and how to refresh them.

**Requirements:** R3, R6, R9.

**Dependencies:** Units 1–6.

**Files:**
- Modify: `DEVELOPMENT.md` (bullet list under "Data flow" naming all four new derived files plus the coverage gaps file)
- Modify: `README.md` (one row in the data-files table if such a table exists; otherwise skip)
- Create: `docs/solutions/raw/2026-05-07-recent-data-capture.md` (one-paragraph note on what was added, the Understat coverage scope, and why UCL/non-top-5 are tracked as gaps not silent zeros)

**Approach:**
- Documentation only. No code.

**Test scenarios:**
- *Test expectation: none — documentation update.*

**Verification:**
- Reading `DEVELOPMENT.md` from scratch tells a new contributor what each new derived file contains, what the coverage gaps file means, and how to refresh them.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Wikipedia DOM changes mid-tournament and breaks the squad pull | Unit 2 includes an HTML fixture test so DOM drift breaks the test, not the data silently |
| `martj42` falls behind and lags an international break | Freshness validator (Unit 6) fails loudly before stale data feeds models |
| Name mismatches between `martj42` and `NAME_TO_FIFA3` cause silent row drops | Unit 1 logs every dropped row to stderr; review the log on first run and patch `NAME_TO_FIFA3` if needed |
| Squad announcements come in waves; a partial squad gets treated as final | `is_final_squad` flag derived from section heading; defaults to False on ambiguity |
| New raw files inflate the gitignored `data/` tree | Existing pattern already gitignores `data/raw/` and `data/derived/`; no new infra |
| Understat rate limits or anti-bot trip during full club pull | Per-team and per-player JSON cached on disk; subsequent runs reuse cache; small inter-request delay matches the existing player-aggregate pull style |
| Player-name resolution misses real players in covered leagues | Two-pass strategy (league-wide fuzzy then within-team fuzzy); unresolved players land in `club_xg_coverage_gaps.parquet` for human review, never silently dropped |
| Non-Understat-league clubs are silently treated as zero-data | `club_xg_coverage_gaps.parquet` lists every such player by name with `reason`; downstream models can fall back to season aggregates or international form for these |
| `football-data.org` free tier rate-limits or removes UCL coverage | Pull is best-effort; missing key produces empty cup-fixtures parquet, not a pipeline abort; freshness validator surfaces the gap |
| UCL/cup match-to-player linking via date+team is wrong (e.g., player rested) | Linking is conservative — only matches where the player's Understat record places them on the club at that date are tagged; rested-player false positives become coverage gaps with `reason=fixture_no_player_link` |
| `xg_available=False` flag is ignored by a downstream consumer | The flag is a column, not a file split, so any consumer that does not check it produces obviously-wrong xG (zero); easy to spot in a smoke check and document explicitly in `methodology/` |

## Sources & References

- Existing pipeline: `tools/pull_wc2026_squads.py`, `tools/pull_understat_players.py`, `tools/weekly_pull.py`, `tools/pull_statsbomb.py`, `tools/build_squad_xg_ratings.py`
- Existing derived data: `data/derived/wc2026_squads.parquet` (currently from empty source), `data/derived/understat_player_xg.parquet`
- Existing raw data: `data/raw/martj42/`, `data/raw/squads/`, `data/raw/understat/`
- External: `https://raw.githubusercontent.com/martj42/international_results/master/results.csv`, `https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads`, `https://understat.com/` (via the `understat` Python package), `https://www.football-data.org/` (free-tier API for UCL and domestic-cup fixtures, no xG)
- Project standards: `DEVELOPMENT.md` (Data contributor track, Reproducibility standard, Data flow)
