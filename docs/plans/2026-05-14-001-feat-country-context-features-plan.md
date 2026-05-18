---
title: "feat: Country-context features (GDP, population, FIFA ranking) for WC2026 model"
type: feat
status: completed
date: 2026-05-14
---

# feat: Country-context features (GDP, population, FIFA ranking) for WC2026 model

## Overview

Add three reference-data features to the WC2026 modeling pipeline, joinable on `team_code`:

1. **GDP per capita (current USD), 1986–2025** — per country, annual.
2. **Total population, 1986–2025** — per country, annual.
3. **Current FIFA world ranking points** — per country, single snapshot.

Source these from free, auth-free public APIs. Land them as raw snapshots under `data/raw/` (role 01) and as curated parquets under `data/derived/` (role 03), keyed by `team_code` so the modeling layer can join trivially.

## Problem Frame

Models today use only on-pitch signal (xG, Elo, form, markets). The user wants macro context — economic scale, population, and the federation's own ranking — as additional features. These are slow-moving, cheap to fetch, and join one-to-one onto `dim_teams`. Scope is the **48 WC2026 qualifiers** (`is_wc2026_qualifier = true` in `db/masters/teams.csv`).

## Requirements Trace

- **R1.** GDP per capita per WC2026 qualifier for the last 40 years (1986–2025 inclusive), one row per (team, year).
- **R2.** Total population per WC2026 qualifier for the last 40 years (1986–2025 inclusive), one row per (team, year).
- **R3.** Current FIFA world ranking points per WC2026 qualifier, one row per team.
- **R4.** Keys join cleanly on `team_code` (FIFA 3-letter) — the canonical key in `db/masters/teams.csv` and the DuckDB `curated.dim_teams`.
- **R5.** Outputs are parquet under `data/derived/`; raw snapshots are dated JSON/CSV under `data/raw/<source>/<YYYY-MM-DD>/` per role 01 contract.
- **R6.** Minimum token spend: do not over-engineer. No new dependencies beyond what `tools/` already uses (`requests` / `httpx`, `pandas`/`pyarrow`).
- **R7. Uniqueness invariant:** the primary-key grain of each parquet is enforced — `(team_code, year)` is unique in `country_gdp_per_capita.parquet` and `country_population.parquet`; `team_code` is unique in `fifa_world_ranking_current.parquet`. No duplicate rows.
- **R8. Last-5-years coverage:** for every WC2026 qualifier (excluding Scotland, which has no World Bank entity), the GDP and population parquets each contain a non-null measure value for every year in `[CURRENT_YEAR - 5, CURRENT_YEAR - 1]` — i.e., the last 5 full years, 2021 through 2025 inclusive at the time of writing. The FIFA ranking parquet has exactly one row per WC2026 qualifier.

## Scope Boundaries

- **In scope:** 48 WC2026 qualifiers, the three named features.
- **Out of scope:** non-qualifier countries (the fetcher can pull them as a side effect if cheaper, but only qualifiers are required to land in `data/derived/`); GDP nominal/PPP variants; historical FIFA ranking time series; per-player wage data.
- **Non-goal:** integrating these into a model. This plan stops at parquet artifacts. The modeling agent picks them up in a separate change.
- **Non-goal:** loading these into DuckDB. The existing `tools/build_duckdb.py` build (or successor) auto-mirrors anything in `data/derived/*.parquet` into the `raw.*` DuckDB schema — these will appear automatically without DB-schema work.

### Deferred to Separate Tasks

- **Model integration:** consuming `country_gdp_per_capita.parquet`, `country_population.parquet`, `fifa_world_ranking_current.parquet` as features happens in a follow-up modeling PR (role 05).
- **Scotland workaround:** Scotland competes as its own FIFA nation but has no World Bank entity (rolled into GBR). Decision below; the actual modeling decision (impute from GBR vs. drop) is the modeler's call.
- **Refresh cadence:** these features are slow-moving (annual / ranking edition). The orchestrator (role 08) can wire a monthly refresh later.

## Context & Research

### Relevant Code and Patterns

- `db/masters/teams.csv` — authoritative team master. `team_code` is canonical; `iso2_code` available for all WC2026 qualifiers except Scotland (`SCO` → no clean ISO2; World Bank rolls into `GBR`).
- `docs/agents/01-data-engineering.md` — defines the `tools/pull_<source>.py` pattern, the `data/raw/<source>/<YYYY-MM-DD>/` layout, and the rule that fetch is the only thing this role does.
- `docs/agents/03-data-cleaning.md` — owner of `data/raw/**` → `data/derived/*.parquet` transformations.
- Existing analogues:
  - `tools/weekly_pull.py` carries the `NAME_TO_FIFA3` / `ISO2_TO_FIFA3` mappings that already cover all WC2026 qualifiers — reuse rather than rebuild.
  - `tools/pull_*` scripts (mentioned in role 01 / acquisition specs) for `requests`-based fetchers with dated output dirs.

### Institutional Learnings

- **Master-data-management** (`memory/feedback_player_identity_registry.md`): dims are sourced from authoritative masters; facts are matched TO dims one-way; never silently extend masters from facts. Applied here: `team_code` is the dim, World Bank / FIFA values are facts joined onto it. ISO2 mapping happens inside the cleaning script, not by mutating `teams.csv`.
- **No FBref** (`DEVELOPMENT.md`): the project hard-blocks FBref. Not relevant here but noting the pattern of "use the cleanest public source, document blocked alternatives."

### External References

- **World Bank Indicators API** — free, public, no auth, supports ISO2 / ISO3 country codes, returns JSON.
  - GDP per capita (current US$): indicator `NY.GDP.PCAP.CD`
    - `https://api.worldbank.org/v2/country/{iso2};{iso2};...;/indicator/NY.GDP.PCAP.CD?date=1986:2025&format=json&per_page=20000`
  - Population, total: indicator `SP.POP.TOTL`
    - `https://api.worldbank.org/v2/country/{iso2};...;/indicator/SP.POP.TOTL?date=1986:2025&format=json&per_page=20000`
  - Semicolon-delimited country list supported — one HTTP call per indicator covers all 48 teams. Two calls total for R1+R2.
- **FIFA world ranking** — no documented public API. The `inside.fifa.com/fifa-world-ranking` page hydrates via JSON XHR. Exact endpoint / response shape is an implementation-time discovery. Primary path: capture the XHR with browser devtools (one-shot, manual) and persist the endpoint URL + `dateId` in the script header. Fallback path: scrape the HTML table from `inside.fifa.com/fifa-world-ranking/men` (table is server-rendered as a static snapshot inside the SPA shell — verify before relying on it). Second fallback: pin to a known community CSV (e.g., a stable GitHub mirror) and document the source.

## Key Technical Decisions

- **Two raw sources, three curated parquets.** World Bank yields both GDP and population (one fetcher); FIFA yields ranking (a second fetcher). Curated layer splits into three parquets so each feature can be joined independently without dragging in irrelevant columns.
- **Bulk World Bank calls.** Use the semicolon-delimited country syntax for one HTTP request per indicator — not 48 × 2 = 96 requests. Polite and cheap.
- **`team_code` as the join key everywhere.** The cleaning script builds the `iso2 → team_code` reverse map from `db/masters/teams.csv` at runtime. World Bank rows arrive keyed by ISO2; FIFA rows arrive keyed by FIFA 3-letter; both are translated to `team_code` before write.
- **Scotland exception, documented not hidden.** World Bank has no Scotland entity. Two options surfaced in the curated artifact: (a) write `SCO` rows with `gdp_per_capita_usd = NULL`, `population = NULL` and a `notes` column reading `"no World Bank entity; modeler may impute from GBR"`; or (b) attribute `GBR` values to `SCO` with a `source_country_code = 'GBR'` column for traceability. **Decision: option (a)** — null-with-note. Imputation is a modeling choice, not a data-engineering one.
- **40 years = 1986–2025 inclusive.** Today is 2026-05-14; 2026 GDP/population are not yet published. Window deliberately ends at last fully-reported year.
- **FIFA ranking endpoint discovery is implementation-time work.** This plan does not commit to a specific URL because the FIFA SPA's XHR shape can change. The script header must document the endpoint actually used so the next refresh is reproducible.
- **No DuckDB schema work in this plan.** The existing build pipeline auto-mirrors `data/derived/*.parquet` into `raw.*`; curated dims/facts that wrap these are a separate concern owned by the DuckDB build agent.

## Open Questions

### Resolved During Planning

- *Which World Bank GDP variant?* → **Current USD (`NY.GDP.PCAP.CD`).** Constant-USD and PPP are stylistic choices for the modeler; current USD is the most-cited default and easiest to interpret.
- *Per-team API calls or bulk?* → **Bulk** (semicolon-delimited countries). Two calls total.
- *Annual or quarterly population?* → **Annual.** Quarterly is not in the World Bank `SP.POP.TOTL` series.
- *Where do these land in DuckDB?* → Out of scope for this plan. The build script auto-discovers `data/derived/*.parquet`.

### Deferred to Implementation

- **FIFA ranking endpoint URL & response shape.** Discover at implementation time; document in the script header. If the SPA XHR is hostile, use the static HTML table on `inside.fifa.com/fifa-world-ranking/men` and parse with BeautifulSoup.
- **Snapshot date semantics for FIFA ranking.** Does the source expose the official "ranking edition" date (a FIFA publishing date) or just a fetch date? Capture both — `ranking_date` (FIFA's edition) and `fetched_at` (wall clock) — when discoverable.
- **Latest pointer / symlink.** Role 01 mentions an optional `data/raw/<source>/latest/` symlink. Add it only if other fetchers in this repo use the same pattern; otherwise skip.

## Implementation Units

- [ ] **Unit 1: World Bank fetcher**

**Goal:** Pull GDP per capita and total population for all WC2026 qualifiers (1986–2025) into dated raw JSON.

**Requirements:** R1, R2, R5, R6

**Dependencies:** None.

**Files:**
- Create: `tools/pull_worldbank.py`
- Create (at runtime): `data/raw/worldbank/2026-05-14/gdp_per_capita.json`
- Create (at runtime): `data/raw/worldbank/2026-05-14/population.json`
- Test: `tests/tools/test_pull_worldbank.py`

**Approach:**
- Load WC2026 qualifiers from `db/masters/teams.csv` (filter `is_wc2026_qualifier = true`), extract non-null `iso2_code` values, build the semicolon-delimited country list.
- Issue two HTTP GETs to the World Bank Indicators API: one for `NY.GDP.PCAP.CD`, one for `SP.POP.TOTL`. Use `date=1986:2025` and `per_page=20000` to ensure a single page. Use the JSON `format`.
- Write the response payload **verbatim** to `data/raw/worldbank/<today>/{gdp_per_capita,population}.json`. No transformation in this script — role 01 contract.
- Idempotent: re-running on the same date overwrites both files. The script's `__main__` accepts an optional `--date` flag for backfilling a specific snapshot dir.
- Document the source URL, indicator codes, and Scotland caveat in the script header.

**Patterns to follow:**
- `tools/pull_*` scripts (e.g., `tools/pull_wc2026_live.py` mentioned in memory and other existing `tools/pull_*.py`) — same shape: dated output dir, polite User-Agent, raw write only.
- Reuse `ISO2_TO_FIFA3` from `tools/weekly_pull.py` if needed for sanity checks; do not duplicate.

**Test scenarios:**
- *Happy path:* Mock the World Bank HTTP response with a small fixture covering 3 countries × 3 years; assert the script writes the raw payload to the expected dated path and the file parses as JSON.
- *Edge case:* `iso2_code` is NULL for Scotland — assert the script does **not** include SCO in the HTTP request (verified via mock call args) and logs a warning.
- *Error path:* World Bank returns HTTP 5xx — assert the script raises (does not silently write an empty file).
- *Edge case:* Response is the World Bank "no data" empty-array shape `[{"page": ..., "total": 0}, null]` — assert the script still writes the raw payload (cleaning is downstream's problem) and exits 0.

**Verification:**
- After a fresh run, both JSON files exist under today's dated dir, are non-empty, and each contain rows for at least 45 of the 47 qualifiers with `iso2_code` populated (Scotland excluded by design; a handful of small-territory misses are tolerated).
- The script is rerunnable: a second run on the same date overwrites cleanly without raising.

---

- [ ] **Unit 2: FIFA ranking fetcher**

**Goal:** Pull the latest FIFA men's world ranking into dated raw JSON or HTML.

**Requirements:** R3, R5, R6

**Dependencies:** None.

**Files:**
- Create: `tools/pull_fifa_rankings.py`
- Create (at runtime): `data/raw/fifa_rankings/2026-05-14/ranking_overview.json` *(or `.html` if HTML scrape fallback is used)*
- Test: `tests/tools/test_pull_fifa_rankings.py`

**Approach:**
- Primary: hit the FIFA inside-site JSON endpoint backing `inside.fifa.com/fifa-world-ranking/men`. Endpoint URL is implementation-time discovery via browser devtools; persist the discovered URL in the script header docstring with the date of discovery so reproducibility is auditable.
- Fallback: if the JSON endpoint is auth-gated or unstable, fetch the rendered HTML at `inside.fifa.com/fifa-world-ranking/men`, save the raw HTML, and leave parsing to Unit 3.
- Persist whatever was fetched (JSON or HTML) verbatim to `data/raw/fifa_rankings/<today>/ranking_overview.{json,html}`.
- Polite headers: realistic User-Agent, single request, no retries beyond one backoff.
- Document the endpoint URL, discovery date, and which path (primary/fallback) the script is using in the header.

**Patterns to follow:**
- Same as Unit 1 — dated output, raw-only write, no transformation.

**Test scenarios:**
- *Happy path:* Mock the FIFA endpoint with a fixture containing 5 ranked teams; assert the script writes the payload verbatim.
- *Error path:* Endpoint returns 403 / auth-gated — assert the script raises with a clear message naming the fallback option, rather than silently writing an empty file.
- *Edge case:* Response is HTML (fallback path active) — assert the file is saved with `.html` extension and content-length > 1KB (sanity).

**Verification:**
- After a run, the dated dir exists and contains a single non-empty file.
- Script header documents the URL it actually hit.

---

- [ ] **Unit 3: Curated parquets — country features**

**Goal:** Transform the raw snapshots from Units 1–2 into three curated parquets keyed by `team_code`.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** Units 1 and 2 must have produced raw snapshots (or fixtures must stand in during tests).

**Files:**
- Create: `tools/build_country_features.py`
- Create (at runtime): `data/derived/country_gdp_per_capita.parquet`
- Create (at runtime): `data/derived/country_population.parquet`
- Create (at runtime): `data/derived/fifa_world_ranking_current.parquet`
- Test: `tests/tools/test_build_country_features.py`

**Approach:**
- Load `db/masters/teams.csv`, build `iso2_to_team_code` (filter to qualifiers; include the Scotland=NULL-iso2 row separately for the explicit-null pass).
- **GDP parquet:** parse `data/raw/worldbank/<latest>/gdp_per_capita.json`, project to `(team_code, year, gdp_per_capita_usd, source_iso2)`, drop World Bank metadata header element, convert year to INTEGER, gdp to DOUBLE. Append a `SCO` row block with `gdp_per_capita_usd = NULL` and `notes = 'no World Bank entity'`. Write to `data/derived/country_gdp_per_capita.parquet`.
- **Population parquet:** identical shape on `SP.POP.TOTL` → `(team_code, year, population, source_iso2)` with the same Scotland-null block. Write to `data/derived/country_population.parquet`.
- **FIFA ranking parquet:** parse the latest `data/raw/fifa_rankings/<latest>/ranking_overview.*`. If JSON, extract per-team rows; if HTML, parse the ranking table with `BeautifulSoup`. Map FIFA's published country codes / names to `team_code` using the existing `NAME_TO_FIFA3` mapping (and a small explicit-mapping fallback for FIFA SPA's casing quirks if any). Project to `(team_code, rank, points, previous_points, ranking_date, fetched_at)`. Filter to WC2026 qualifiers. Write to `data/derived/fifa_world_ranking_current.parquet`.
- Quarantine unmatched rows: if a FIFA-source team name fails to resolve to a `team_code` for a WC2026 qualifier, write the unresolved row to `data/derived/fifa_world_ranking_quarantine.csv` (or include in the script log) and surface as a script-exit warning — never silently drop.
- Idempotent: rerunning overwrites the parquets atomically.

**Patterns to follow:**
- `tools/refresh_player_master.py` and `tools/build_duckdb.py` for the "match facts to masters, quarantine unmatched, never extend masters silently" pattern (per `memory/feedback_player_identity_registry.md`).
- Other cleaners under `tools/` for the raw-JSON → parquet shape and pyarrow write conventions.

**Test scenarios:**
- *Happy path (GDP):* Given a small World Bank fixture with 3 countries × 2 years, assert the output parquet has 6 rows, correct dtypes (`year: int32`, `gdp_per_capita_usd: float64`), and `team_code` correctly mapped from `iso2`.
- *Happy path (population):* Symmetric to GDP, asserting `population` column is float64 (World Bank returns floats even for population) and non-negative.
- *Happy path (FIFA):* Given a FIFA fixture (JSON or HTML) for 5 teams, assert the parquet contains a `points` column, `rank` is monotone-increasing, and only WC2026 qualifiers appear.
- *Edge case:* Scotland row is present in GDP and population parquets with `gdp_per_capita_usd = NULL` / `population = NULL` and a populated `notes` column.
- *Edge case:* A World Bank entry has `value: null` for a (country, year) cell — assert the row is still emitted with `gdp_per_capita_usd = NULL` rather than skipped (so the time series is gap-explicit, not gap-implicit).
- *Error path (FIFA quarantine):* A FIFA-source row carries a country name unknown to `NAME_TO_FIFA3` — assert it is written to the quarantine CSV with a `reason` column, and the script exits with a non-zero return *only* if the unmatched row corresponds to a WC2026 qualifier (unmatched non-qualifiers are fine to drop quietly).
- *Integration:* Run end-to-end with real (small) snapshots in a tmpdir, then read each parquet with `pyarrow` and verify it joins one-to-one onto `db/masters/teams.csv` filtered to WC2026 qualifiers, with at most 1 missing row (Scotland for World Bank features).
- *Uniqueness (R7) — GDP & population:* After write, `df.groupby(['team_code', 'year']).size().max() == 1` — no duplicate (team, year) pairs in either parquet.
- *Uniqueness (R7) — FIFA:* After write, `df['team_code'].is_unique` is True in the FIFA ranking parquet.
- *Last-5-years coverage (R8) — GDP:* For every WC2026 qualifier with `iso2_code IS NOT NULL` (i.e., all qualifiers except Scotland), and for each year in `{2021, 2022, 2023, 2024, 2025}`, exactly one row exists with `gdp_per_capita_usd IS NOT NULL`. Assertion fails fast naming the missing `(team_code, year)` pairs.
- *Last-5-years coverage (R8) — population:* Symmetric for `population`.
- *Last-5-years coverage (R8) — FIFA:* For every WC2026 qualifier, exactly one row exists in the FIFA ranking parquet with `points IS NOT NULL`.
- *Coverage edge case:* If the World Bank response is missing 2025 data for a qualifier (sometimes the very latest year is reported late), the script logs an explicit warning with the team and year, **and the test fails** — surfacing the gap rather than silently shipping partial data. The implementer's remediation path is documented in the script header (re-fetch later, or temporarily exclude that team from training).

**Verification:**
- All three parquets exist under `data/derived/` after a run.
- Row counts match expectations: GDP and population each have ≈47 teams × 40 years ≈ 1,880 rows plus a Scotland null-block of 40 rows; FIFA ranking has exactly 48 rows (one per qualifier).
- Each parquet round-trips: `pd.read_parquet(...)` succeeds and `team_code` is a non-null string of length 3.
- **Uniqueness:** `df.groupby(['team_code', 'year']).size().max() == 1` for GDP and population; `df['team_code'].is_unique` for FIFA ranking.
- **Last-5-years coverage:** for every WC2026 qualifier except Scotland, GDP and population parquets have a non-null measure for each year `{2021..2025}`; FIFA parquet has one non-null `points` per qualifier (48/48).
- The build script logs a `MATCHED 48/48 WC2026 qualifiers` summary line (or, for GDP/population, `MATCHED 47/48 — SCO null-block by design`).

## System-Wide Impact

- **Interaction graph:** `tools/build_duckdb.py` (or successor) auto-mirrors `data/derived/*.parquet` into `raw.*` — three new parquets will appear as `raw.country_gdp_per_capita`, `raw.country_population`, `raw.fifa_world_ranking_current` on the next DuckDB rebuild without any DDL change. Modeling agent picks them up from there.
- **Error propagation:** Unit 3 quarantines unmatched FIFA rows and surfaces them; it does not extend `teams.csv` or invent codes. Master-data-management invariant preserved.
- **State lifecycle risks:** Raw snapshots are dated and immutable. Derived parquets are overwritten atomically. No partial-write risk if the script writes to a tempfile and renames at the end (recommended).
- **API surface parity:** None — these are reference-data adds, not changes to existing interfaces.
- **Integration coverage:** Unit 3's integration test reads from real-shaped fixtures and asserts the join-key invariant against the live `db/masters/teams.csv`.
- **Unchanged invariants:** `db/masters/teams.csv` is read-only here. The matching layer in `tools/build_duckdb.py` is not modified. No DuckDB schema migrations are introduced.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| World Bank API rate-limits or returns a partial page. | Use `per_page=20000` (single page), polite User-Agent, and a short retry-once-on-5xx. Raw write preserves whatever was returned; cleaning can detect partial pages. |
| FIFA ranking SPA changes endpoint shape. | Document the discovered endpoint in the script header; provide HTML-scrape fallback; quarantine unmatched rows rather than failing the whole run. |
| `iso2_code` is missing or wrong for a future-added qualifier. | Unit 1 logs and excludes; Unit 3's "MATCHED N/48" verification line surfaces the gap on every run. |
| Scotland-NULL rows are silently consumed by a downstream model as zero. | Add the `notes` column explicitly, and call out the choice in the parquet's schema. Modeler must opt into imputation. |
| Two parquets (GDP, population) tempting to merge into one wide table. | Keep separated. Modeler can join on `(team_code, year)`; concatenation premature. |

## Documentation / Operational Notes

- Each new `tools/pull_*.py` and `tools/build_*.py` carries a top-of-file docstring with: source URL, indicator code (where relevant), update cadence ("annual for World Bank; per FIFA ranking edition (~6 / year)"), and known gotchas (Scotland).
- No new env vars, no new API keys.
- Slow-moving data: no orchestrator wiring needed for now. A one-line entry can be added to role 08's monthly schedule in a follow-up.

## Sources & References

- World Bank Indicators API docs: `https://datahelpdesk.worldbank.org/knowledgebase/articles/889392`
- World Bank GDP per capita (current US$): `NY.GDP.PCAP.CD`
- World Bank Population, total: `SP.POP.TOTL`
- FIFA men's world ranking: `https://inside.fifa.com/fifa-world-ranking/men` (endpoint discovery at implementation time)
- Project conventions:
  - `docs/agents/01-data-engineering.md` — fetch contract
  - `docs/agents/03-data-cleaning.md` — transformation contract
  - `db/SCHEMA.md` — MDM model and teams master
  - `db/masters/teams.csv` — authoritative team list with `iso2_code` and `is_wc2026_qualifier`
- Related code: `tools/weekly_pull.py` (carries `ISO2_TO_FIFA3` and `NAME_TO_FIFA3`).
