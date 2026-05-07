---
title: "feat: Capture recent games and announced WC2026 squads"
type: feat
status: active
date: 2026-05-07
---

# feat: Capture recent games and announced WC2026 squads

## Overview

Models read from `data/derived/`, but two upstream gaps mean models are training on stale inputs:

1. The international-match record stops at Copa America 2024 (July 2024). Roughly ten months of international football — UEFA Nations League 2024-25, FIFA WC qualifying windows (Sep/Oct/Nov 2024, March/June/Sep/Oct/Nov 2025, March 2026), and pre-tournament friendlies — never reach `data/derived/`.
2. `data/raw/squads/wc2026_squads_raw.json` is an empty array. The Wikipedia squad scrape is not producing rows, so `data/derived/wc2026_squads.parquet` is built from an empty source. WC2026 squad announcements are happening now (tournament starts 2026-06-11).

This plan adds two pulls and one validation step so the most recent games and announced players land in `data/derived/` cleanly, dated, and idempotently — ready for downstream models. Cleaning means: schema conformance, deduplication, name normalization, and a freshness check that fails loudly. It does **not** mean re-deriving xG, fitting models, or correcting historical bias — those are separate concerns.

## Problem Frame

A data engineer's job here is to deliver fresh, schema-correct inputs to the modeling layer. Today the pipeline produces correct outputs from stale inputs. Concretely:

- `data/derived/statsbomb_team_xg.parquet` covers WC2018, Euro2020, WC2022, Euro2024, Copa2024 — nothing past 2024-07-14. StatsBomb open-data does not publish UEFA Nations League or WC qualifiers, so a non-StatsBomb source is required for recency.
- `data/derived/wc2026_squads.parquet` is empty (built from `[]`). Models that should read from announced rosters fall back to whatever proxy they have (likely the most recent tournament squads), which is exactly the bias this pipeline was built to avoid.
- `data/raw/martj42/2026-04-28/` exists, suggesting `martj42/international_results` is already pulled, but no derived match-level table is produced for downstream consumers — the file is read inline by `weekly_pull.py` for Elo and never persisted in cleansed form.
- `tools/pull_fbref_national.py` exists but FBref is hard-blocked by Cloudflare (`DEVELOPMENT.md`). Treat that file as unusable for this plan.

## Requirements Trace

- R1. `data/derived/recent_internationals.parquet` exists and contains every full international match from 2024-08-01 through the most recent international break, in a documented schema (date, home, away, home_goals, away_goals, competition, source).
- R2. `data/derived/wc2026_squads.parquet` is non-empty and contains player rows for every nation listed on the Wikipedia squads page, with `nation`, `player`, `position`, `club`, and `is_final_squad` boolean.
- R3. Both pulls are idempotent: re-running on the same day produces the same outputs; running on a later day adds new matches and updates squad announcements without duplicating prior rows.
- R4. Both pulls write date-stamped raw snapshots to `data/raw/<source>/<YYYY-MM-DD>/` and the most recent snapshot to a `latest/` symlink-equivalent (matches existing `martj42` pattern).
- R5. A freshness validator fails loudly when either derived parquet is older than a configured threshold (matches stale > 14 days; squads stale > 7 days during May/June 2026).
- R6. The two new pulls plug into `tools/weekly_pull.py` so a single `python3 tools/weekly_pull.py` produces refreshed inputs.

## Scope Boundaries

- **Not** computing xG for the recent matches. xG requires shot-level event data (StatsBomb-quality), which `martj42` does not provide. Recent games come in goal-only.
- **Not** changing any model code. Models continue reading the existing parquet schemas; the new files are *additive*.
- **Not** auditing or correcting existing data (the prior version of this plan covered that — it was out of scope for "data engineer captures recent data").
- **Not** building shrinkage priors, manual override layers, or audit reports. Those are separate plans if they're needed.
- **Not** pulling FBref. Hard-blocked.
- **Not** pulling Understat for new tournaments — Understat is club-only.

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

## Open Questions

### Resolved During Planning

- **Should we attempt to derive xG for recent matches?** No. Out of scope; goals-only is enough for Elo/form features. (If a future model needs xG for recent matches, that's a separate plan with a separate source decision.)
- **Where do final-squad rows come from when Wikipedia hasn't been updated yet?** Wikipedia's squads page tracks both preliminary (35-player) and final (26-player) lists; `is_final_squad` is False until Wikipedia flips them. Re-running the pull picks up the change.
- **Should non-WC2026 nations be included in `recent_internationals.parquet`?** Yes — the file mirrors `martj42` faithfully so it's reusable for non-WC contexts (Elo updates, form features). Consumers filter by FIFA3 code.

### Deferred to Implementation

- Why is `pull_wc2026_squads.py` currently producing `[]`? Root cause is unknown until Unit 2 runs; could be Wikipedia DOM change, BeautifulSoup selector drift, or an upstream redirect. Diagnosis happens in-unit.
- Exact freshness thresholds (14 days for matches; 7 days for squads in May/June 2026, 30 days otherwise) — these are starting values. Adjust in Unit 4 once the validator runs against real data.

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

- [ ] **Unit 3: Wire both pulls into `weekly_pull.py`**

**Goal:** A single `python3 tools/weekly_pull.py` invocation refreshes both new parquets.

**Requirements:** R6.

**Dependencies:** Units 1, 2.

**Files:**
- Modify: `tools/weekly_pull.py`

**Approach:**
- Add the two pulls to the orchestrator's existing run sequence (matches the pattern already in place for Kalshi, Polymarket, Elo).
- Each pull is wrapped so a single source failure does not abort the whole run; failures are logged and surfaced at the end.
- No change to the existing comparison-table logic.

**Test scenarios:**
- Happy path — End-to-end `weekly_pull.py` run produces both parquets and the existing comparison table without errors.
- Edge case — Wikipedia is unreachable during the run; squad pull logs the failure, match pull still completes, comparison table still builds from remaining inputs.

**Verification:**
- Running `python3 tools/weekly_pull.py 2026-05-07` from a clean tree produces both new parquets.

---

- [ ] **Unit 4: Freshness validator**

**Goal:** A standalone check that fails loudly when derived data is stale, callable from `weekly_pull.py` and CI.

**Requirements:** R5.

**Dependencies:** Units 1, 2.

**Files:**
- Create: `tools/check_data_freshness.py`
- Modify: `tools/weekly_pull.py` (call the validator at end of run)
- Test: `tools/test_check_data_freshness.py`

**Approach:**
- Read `recent_internationals.parquet` and `wc2026_squads.parquet`. Compute the most recent match date and the most recent `scraped_date`.
- Configured thresholds (constants at top of file): `MATCHES_MAX_AGE_DAYS = 14`, `SQUADS_MAX_AGE_DAYS_TOURNAMENT = 7`, `SQUADS_MAX_AGE_DAYS_DEFAULT = 30`. Squad threshold tightens automatically between 2026-05-15 and 2026-07-15.
- Exit code 0 = fresh, 1 = stale (with a printed reason), 2 = file missing.
- No network calls; pure reads of the derived parquets.

**Test scenarios:**
- Happy path — Both files current; exit 0.
- Edge case — Match file's most recent date is 20 days ago; exit 1, message names the offending file and age.
- Edge case — Squad file missing entirely; exit 2.
- Edge case — Today's date is during the tournament window (June 2026); squad-staleness threshold is 7 days, not 30.

**Verification:**
- The validator runs in under 5 seconds.
- A staged staleness scenario (artificially old parquet) produces a clear actionable error.

---

- [ ] **Unit 5: Document and ship**

**Goal:** Update docs so future contributors know what these new files contain and how to refresh them.

**Requirements:** R3, R6.

**Dependencies:** Units 1–4.

**Files:**
- Modify: `DEVELOPMENT.md` (one bullet under "Data flow" listing the two new derived files)
- Modify: `README.md` (one row in the data-files table if such a table exists; otherwise skip)
- Create: `docs/solutions/raw/2026-05-07-recent-data-capture.md` (one-paragraph note on what was added and why)

**Approach:**
- Documentation only. No code.

**Test scenarios:**
- *Test expectation: none — documentation update.*

**Verification:**
- Reading `DEVELOPMENT.md` from scratch tells a new contributor what `recent_internationals.parquet` and `wc2026_squads.parquet` contain and how to refresh them.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Wikipedia DOM changes mid-tournament and breaks the squad pull | Unit 2 includes an HTML fixture test so DOM drift breaks the test, not the data silently |
| `martj42` falls behind and lags an international break | Freshness validator (Unit 4) fails loudly before stale data feeds models |
| Name mismatches between `martj42` and `NAME_TO_FIFA3` cause silent row drops | Unit 1 logs every dropped row to stderr; review the log on first run and patch `NAME_TO_FIFA3` if needed |
| Squad announcements come in waves; a partial squad gets treated as final | `is_final_squad` flag derived from section heading; defaults to False on ambiguity |
| New raw files inflate the gitignored `data/` tree | Existing pattern already gitignores `data/raw/` and `data/derived/`; no new infra |

## Sources & References

- Existing pipeline: `tools/pull_wc2026_squads.py`, `tools/weekly_pull.py`, `tools/pull_statsbomb.py`
- Existing derived data: `data/derived/wc2026_squads.parquet` (currently from empty source)
- Existing raw data: `data/raw/martj42/`, `data/raw/squads/`
- External: `https://raw.githubusercontent.com/martj42/international_results/master/results.csv`, `https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads`
- Project standards: `DEVELOPMENT.md` (Data contributor track, Reproducibility standard, Data flow)
