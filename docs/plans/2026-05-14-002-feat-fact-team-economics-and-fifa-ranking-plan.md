---
title: "feat: Wire country-context parquets into DuckDB as fact_team_economics + fact_team_fifa_ranking"
type: feat
status: completed
date: 2026-05-14
origin: docs/plans/2026-05-14-001-feat-country-context-features-plan.md
---

# feat: Wire country-context parquets into DuckDB as `fact_team_economics` + `fact_team_fifa_ranking`

## Overview

The prior plan (`docs/plans/2026-05-14-001-feat-country-context-features-plan.md`) produces three parquets in `data/derived/`:

- `country_gdp_per_capita.parquet` — (team_code, year, gdp_per_capita_usd, …)
- `country_population.parquet` — (team_code, year, population, …)
- `fifa_world_ranking_current.parquet` — (team_code, rank, points, …)

This plan wires those into the DuckDB MDM at `data/wc2026.duckdb` so the modeling layer can join them against `curated.dim_team` via SQL:

- Register parquets in the `raw.*` schema (existing `tools/build_duckdb.py` mechanism).
- Build two normalized curated facts:
  - `curated.fact_team_economics` — **one row per (team_code, year)**, combining GDP and population at the same grain.
  - `curated.fact_team_fifa_ranking` — one row per (team_code, snapshot_date) for the current FIFA ranking; designed so future snapshots accumulate.
- Quarantine any source row whose `team_code` does not resolve to `curated.dim_team`.
- Build one denormalized view on top:
  - `curated.dim_team_current` — `dim_team` enriched with the latest economics row and current FIFA ranking. Model code reads this single view to get every team feature in one query.
- Add verification (FK orphan check, row-count gate, latest-year completeness, view-coverage check) and one example query.

**Layer model:** the two facts are the normalized truth (time series + snapshot grain); the view is the denormalized convenience layer modelers consume. Storage cost of the view is zero (DuckDB views are query-time).

## Problem Frame

The user wants World Bank macro features and FIFA ranking joinable in DuckDB. The parquets exist (or will, after Plan 001) and are already keyed on `team_code`, which matches `curated.dim_team`'s natural key. Matching is therefore a direct join — no `staging.team_name_resolution` layer needed. What remains is the standard MDM plumbing: register raw, build fact, enforce dim integrity, surface unmatched rows.

## Requirements Trace

- **R1.** A `curated.fact_team_economics` table exists in `data/wc2026.duckdb`, with one row per `(team_code, year)` and columns for `gdp_per_capita_usd` and `population`.
- **R2.** A `curated.fact_team_fifa_ranking` table exists, with one row per `(team_code, snapshot_date)` carrying current rank and points.
- **R3.** Every row in both facts has a `team_code` that exists in `curated.dim_team` (foreign-key integrity, enforced at build time via LEFT-JOIN-then-filter).
- **R4.** Source rows whose `team_code` does not match `curated.dim_team` are written to `quarantine.unmatched_team_economics` / `quarantine.unmatched_team_fifa_ranking` rather than dropped silently.
- **R5.** A `curated.dim_team_current` view exposes `dim_team` joined to the **latest** economics row and the current FIFA ranking, so model code reads one table to get every team feature.
- **R6.** `tools/build_duckdb.py` rebuilds the facts and the view idempotently as part of the existing pipeline.
- **R7.** `db/sql/verify_duckdb.py` reports row counts, orphan checks, and view coverage for the new artifacts.
- **R8.** `db/SCHEMA.md` is updated so the contract is documented.
- **R9.** All curated SQL uses CTEs declared up front and LEFT JOINs against the dim with explicit `WHERE … IS NULL` / `IS NOT NULL` splits — no inline subqueries, no `INNER JOIN` shortcuts. (Readability rule.)
- **R10. Uniqueness (no duplicate keys) enforced at build time:**
  - `curated.fact_team_economics`: `(team_code, year)` is unique. Zero duplicate `(team_code, year)` pairs.
  - `curated.fact_team_fifa_ranking`: `(team_code, snapshot_date)` is unique; equivalently with the current single-snapshot grain, `team_code` is unique.
  - `curated.dim_team_current`: `team_code` is unique (one row per team).
- **R11. Last-5-years coverage:** for every WC2026 qualifier, `curated.fact_team_economics` contains a row for each of the last 5 calendar years (`MAX(year) - 4` through `MAX(year)`) with at least one non-null measure. Scotland is exempt for the measure-non-null part but still must have row presence for those years (NULL rows are acceptable). FIFA ranking covers all 48 qualifiers in its single snapshot.

## Scope Boundaries

- **In scope:** raw load, two curated facts, quarantine, the `dim_team_current` view, verification, schema doc, one example query.
- **Out of scope:** changes to `curated.dim_team` itself (it already exists and is correct — the view layers on top, the base dim is unchanged); FIFA ranking historical time series; modeling consumption.
- **Non-goal:** introducing a `staging.team_name_resolution`-style layer for these sources. The parquets are already keyed on `team_code`, so the staging step adds no value here. If a future source for the same measures lands without a `team_code`, that source can introduce its own staging.
- **Non-goal:** denormalizing fact columns directly onto `curated.dim_team`. The view (`dim_team_current`) gives the same read ergonomics without breaking the MDM rule that dims project from masters, not facts.

### Deferred to Separate Tasks

- **FIFA ranking history.** The fact table is shaped to accumulate snapshots, but no historical backfill happens in this plan.
- **Modeling integration.** A follow-up modeling PR (role 05) joins `fact_team_economics` and `fact_team_fifa_ranking` against `dim_team` to produce model features.
- **Refresh scheduling.** Orchestrator (role 08) can later wire a monthly refresh.

## Context & Research

### Relevant Code and Patterns

- `tools/build_duckdb.py` — canonical build. Carries:
  - `RAW_TABLES: list[(parquet_filename, raw_table_name)]` — new parquets register here.
  - `DIM_SQL_FILES: list[str]` — dim SQL files.
  - The script already has phase scaffolding for `match` and `facts` (see header docstring).
- `db/sql/curated/dim_team.sql` — current dim. `team_code` is the natural primary key (no surrogate). Loaded from `db/masters/teams.csv` with `nullstr=''`.
- `db/sql/curated/fact_team_rating.sql` — existing fact precedent. Uses `staging.team_name_resolution` because its sources are keyed by `nation` (free-form). We **do not** need that here — the join is direct on `team_code`.
- `db/sql/curated/fact_player_xg.sql` (assumed; symmetric file present) — second fact precedent.
- `db/SCHEMA.md` — the contract doc; must be updated when facts are added.
- `db/sql/verify_duckdb.py` — row-count and integrity checks.
- `db/queries/examples/` — directory for analyst-facing example queries.

### Institutional Learnings

- **Master-data-management** (`memory/feedback_player_identity_registry.md`): facts reference dims via stable keys; never silently extend masters; quarantine unmatched. This is directly the pattern here.
- **`CREATE OR REPLACE` everywhere** (`db/SCHEMA.md`): every curated table is rebuilt on each run. No migrations. No append-mode logic.
- **Naming nit:** the existing dim is `curated.dim_team` (singular), not `dim_teams`. Plan 001 referenced `dim_teams` in prose; this plan uses the correct singular form. Update Plan 001 if a refresh pass happens, but it has no functional consequence — Plan 001's outputs are parquets, not DuckDB tables.

### External References

None — purely internal plumbing.

## Key Technical Decisions

- **One fact table for GDP + population, not two.** Both share the `(team_code, year)` grain; combining them avoids a redundant join in every downstream query. The fact is named `fact_team_economics` (not the user's literal `fact_team`) because `fact_team` would overload with `dim_team` and the existing precedent is `fact_team_rating` — i.e., `fact_<entity>_<measure-cluster>`. The user-facing concept ("one row per team-year") is preserved.
- **FIFA ranking is a separate fact with grain `(team_code, snapshot_date)`.** Different grain from the time-series economics fact — combining them would force fake date alignment. Designed so multiple snapshots can accumulate over time (currently 1 row per team).
- **Direct join, no staging layer.** Plan 001's cleaner already maps `iso2 → team_code` for World Bank and FIFA-source-name → `team_code` for the FIFA ranking. The curated fact SQL is therefore a thin projection + integrity filter, not a name-resolution exercise.
- **Normalized facts + denormalized view.** Two-layer model: facts hold the truth at native grain (40 years × team for economics; one snapshot per team for ranking). The `dim_team_current` view denormalizes the latest row of each fact onto the dim so model SQL reads one table. Best of both — normalized storage, denormalized read.
- **`dim_team_current` is a `VIEW`, not a `TABLE`.** Recomputes at query time, never goes stale, zero storage, zero rebuild ordering concern. The cost is recomputing a 48-row window function on read — trivial.
- **SQL readability bar.** Every curated SQL file uses the same shape: `WITH` clause declaring named CTEs top-to-bottom in data-flow order, then a single terminal `SELECT`. LEFT JOIN dim_team then `WHERE dim_team_code IS NOT NULL` (fact) or `IS NULL` (quarantine). No inline subqueries inside FROM, no clever one-liners. The implementer should be able to read the SQL top-down like prose.
- **Quarantine on `LEFT JOIN dim_team WHERE team_code IS NULL`**, then the fact gets the inverse via `INNER JOIN`. Two SQL files per fact — one for the fact, one for the quarantine. Mirrors the existing `staging` / `quarantine` split.
- **FK integrity always; completeness only for the latest year.** The fact's `INNER JOIN curated.dim_team` enforces that every row's `team_code` exists in the dim — this applies to all 40 years (data hygiene; non-negotiable). The *completeness* assertion (every WC2026 qualifier has a row) only applies for the **latest available year** in the data (currently 2025). Older years legitimately have gaps — Yugoslavia successor states pre-1991, USSR successor states pre-1991, South Sudan pre-2011, etc. — and World Bank rightly reports NULL or omits those rows. Asserting full qualifier coverage for the entire time series would be false-positive bait. For FIFA ranking the completeness rule is straightforward: 48 rows, one per qualifier, single snapshot.
- **`snapshot_date` on the FIFA fact, sourced from the parquet's `ranking_date` column if available, else `fetched_at`, else `CURRENT_DATE` at build time.** Documented in the SQL.
- **40-year window assertion in verify.** Economics fact should have ~47 teams × 40 years ≈ 1,880 rows ± a small allowance for missing-year cells (World Bank sometimes returns NULLs for early years for smaller economies). Scotland's null-block contributes 40 more rows. Verify asserts the range, not an exact count.

## Open Questions

### Resolved During Planning

- *Combine GDP + population into one fact?* → **Yes** (shared grain).
- *Name the fact `fact_team`?* → **No** — `fact_team_economics`. Avoids overload with `dim_team`; mirrors `fact_team_rating` naming.
- *Need a staging layer?* → **No** — parquets are already keyed on `team_code`.
- *Where does verification live?* → Extend `db/sql/verify_duckdb.py`; do not introduce a new verifier.

### Deferred to Implementation

- *Exact column set of the FIFA ranking parquet.* Plan 001 names `rank, points, previous_points, ranking_date, fetched_at`. If the implementer of Plan 001 finalizes a different set, the fact SQL adapts to whatever columns are actually present. The contract enforced here is: `team_code`, `rank`, `points`, and at least one date-ish column.
- *Whether `previous_points` is meaningful.* Depends on whether the FIFA endpoint exposes it. If absent, drop the column from the fact.

## Implementation Units

- [ ] **Unit 1: Register the three parquets in `raw.*`**

**Goal:** The three new parquets load into `raw.country_gdp_per_capita`, `raw.country_population`, `raw.fifa_world_ranking_current` on every build.

**Requirements:** R1, R2, R5

**Dependencies:** Plan 001 has produced the parquets (or fixtures exist for testing).

**Files:**
- Modify: `tools/build_duckdb.py` — extend `RAW_TABLES` with three entries.
- Test: `tests/db/test_build_duckdb_country_features.py` (or extend the existing build test if one exists).

**Approach:**
- Add three tuples to `RAW_TABLES`:
  ```
  ("country_gdp_per_capita.parquet",       "country_gdp_per_capita"),
  ("country_population.parquet",           "country_population"),
  ("fifa_world_ranking_current.parquet",   "fifa_world_ranking_current"),
  ```
- No code-flow change needed; the existing `load_raw` loop handles them.
- If any parquet is missing on disk, the existing `ERROR: missing parquet` branch already aborts the build — confirm the error message is actionable (mentions which file).

**Patterns to follow:**
- Existing `RAW_TABLES` entries in `tools/build_duckdb.py:41`.

**Test scenarios:**
- *Happy path:* With the three parquets present (real or fixtures), running the build creates `raw.country_gdp_per_capita`, `raw.country_population`, `raw.fifa_world_ranking_current` with row counts > 0.
- *Error path:* If `country_gdp_per_capita.parquet` is missing, the build aborts with a clear `ERROR: missing parquet …country_gdp_per_capita.parquet` message and a non-zero exit code.
- *Edge case:* Re-running the build on the same DB file produces the same row counts (idempotency).

**Verification:**
- `SELECT COUNT(*) FROM raw.country_gdp_per_capita` returns > 0 after build.
- The same query for the other two raw tables also returns > 0.

---

- [ ] **Unit 2: `curated.fact_team_economics` + quarantine**

**Goal:** Build a curated fact with one row per (team_code, year), combining GDP and population, with full join coverage against `dim_team`.

**Requirements:** R1, R3, R4, R5

**Dependencies:** Unit 1.

**Files:**
- Create: `db/sql/curated/fact_team_economics.sql`
- Create: `db/sql/quarantine/unmatched_team_economics.sql` *(or inline as a second statement in the fact SQL — pick whichever matches the existing precedent for `fact_team_rating`)*
- Modify: `tools/build_duckdb.py` — register the new fact SQL in a `FACT_SQL_FILES` list (introduce one if it does not exist yet) and the quarantine SQL in a `QUARANTINE_SQL_FILES` list (same).
- Test: `tests/db/test_fact_team_economics.py`

**Approach:**
- **SQL style: CTEs first, LEFT JOIN against `dim_team`, split at the end.** Every named transformation gets its own CTE at the top so a human reader can follow the data flow top-to-bottom. The FK split (matched → fact, unmatched → quarantine) uses a single `LEFT JOIN dim_team` followed by `WHERE`-clause filtering — never two separate scans of the raw data.
- The SQL builds the fact as:
  ```sql
  CREATE OR REPLACE TABLE curated.fact_team_economics AS
  WITH
  gdp_raw AS (
      SELECT team_code, year, gdp_per_capita_usd
      FROM raw.country_gdp_per_capita
  ),
  pop_raw AS (
      SELECT team_code, year, population
      FROM raw.country_population
  ),
  merged AS (
      -- FULL OUTER so a (team, year) with only one of the two measures still appears.
      SELECT
          COALESCE(g.team_code, p.team_code) AS team_code,
          COALESCE(g.year,       p.year)     AS year,
          g.gdp_per_capita_usd,
          p.population
      FROM gdp_raw g
      FULL OUTER JOIN pop_raw p USING (team_code, year)
  ),
  resolved AS (
      -- LEFT JOIN dim_team: unmatched rows have d.team_code IS NULL and route to quarantine.
      SELECT
          m.team_code,
          m.year,
          m.gdp_per_capita_usd,
          m.population,
          d.team_code AS dim_team_code
      FROM merged m
      LEFT JOIN curated.dim_team d ON d.team_code = m.team_code
  )
  SELECT team_code, year, gdp_per_capita_usd, population
  FROM resolved
  WHERE dim_team_code IS NOT NULL;
  ```
  *(Directional sketch — directional guidance for review, not implementation specification. The implementer should match the comment header conventions in `db/sql/curated/fact_team_rating.sql`.)*
- The quarantine SQL is the inverse — same CTE pipeline, opposite `WHERE` filter:
  ```sql
  CREATE OR REPLACE TABLE quarantine.unmatched_team_economics AS
  WITH
  gdp_raw AS (SELECT team_code, year, gdp_per_capita_usd, 'gdp' AS source FROM raw.country_gdp_per_capita),
  pop_raw AS (SELECT team_code, year, population,            'population' AS source FROM raw.country_population),
  unioned AS (
      SELECT team_code, year, gdp_per_capita_usd, NULL::DOUBLE AS population, source FROM gdp_raw
      UNION ALL
      SELECT team_code, year, NULL::DOUBLE AS gdp_per_capita_usd, population,  source FROM pop_raw
  ),
  resolved AS (
      SELECT u.*, d.team_code AS dim_team_code
      FROM unioned u
      LEFT JOIN curated.dim_team d ON d.team_code = u.team_code
  )
  SELECT
      team_code, year, gdp_per_capita_usd, population, source,
      'team_code not in dim_team' AS reason
  FROM resolved
  WHERE dim_team_code IS NULL;
  ```
- Scotland (`SCO`) rows from the parquets (null GDP, null population — emitted by Plan 001) survive the LEFT-JOIN-then-filter (Scotland is in `dim_team`) and appear in the fact with NULL measures. That is correct behavior — the data engineer's null becomes the fact's null.

**Patterns to follow:**
- `db/sql/curated/fact_team_rating.sql` — header docstring, `CREATE OR REPLACE`, explicit `CAST` to numeric types.
- `db/sql/curated/dim_team.sql` — terse comment style at top.

**Test scenarios:**
- *Happy path:* With fixture `raw` tables containing 3 teams × 3 years for both GDP and population, the fact has 9 rows, each with both measures populated.
- *Edge case (FULL OUTER):* GDP has a year that population is missing; the fact still emits that row with `population = NULL`.
- *Edge case (Scotland-shaped):* A team in `dim_team` with NULL measure values in the parquets appears in the fact with NULL measure values (not dropped).
- *Error path:* A raw row has `team_code = 'XYZ'` not in `dim_team` — assert it lands in `quarantine.unmatched_team_economics` with `reason = 'team_code not in dim_team'` and **does not** appear in `curated.fact_team_economics`.
- *Integration:* `SELECT d.team_name, f.year, f.gdp_per_capita_usd, f.population FROM curated.fact_team_economics f JOIN curated.dim_team d USING (team_code) WHERE d.is_wc2026_qualifier LIMIT 10` returns rows with all four columns populated for at least 10 WC2026 qualifiers in 2024.
- *Uniqueness (R10):* `SELECT team_code, year, COUNT(*) AS n FROM curated.fact_team_economics GROUP BY 1, 2 HAVING n > 1` returns zero rows.
- *Last-5-years coverage (R11):* `SELECT d.team_code, y.year FROM curated.dim_team d CROSS JOIN (SELECT DISTINCT year FROM curated.fact_team_economics WHERE year >= (SELECT MAX(year) - 4 FROM curated.fact_team_economics)) y LEFT JOIN curated.fact_team_economics f USING (team_code, year) WHERE d.is_wc2026_qualifier AND f.team_code IS NULL` returns zero rows — every WC2026 qualifier has a row for each of the last 5 years.

**Verification:**
- `SELECT MIN(year), MAX(year) FROM curated.fact_team_economics` is `(1986, 2025)`.
- **Latest-year completeness (the hard gate):** `SELECT COUNT(DISTINCT team_code) FROM curated.fact_team_economics WHERE year = (SELECT MAX(year) FROM curated.fact_team_economics) AND team_code IN (SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier)` returns 48 (or 47 if Scotland's all-NULL row was filtered — explicitly document the choice). This is what verify enforces.
- **Earlier-year coverage (informational only):** verify reports the count but does **not** fail if a 1986 row is missing for, say, Bosnia and Herzegovina or Uzbekistan — those countries did not exist in 1986 and World Bank correctly has no row.
- `SELECT COUNT(*) FROM quarantine.unmatched_team_economics WHERE team_code IN (SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier)` returns 0 (FK integrity, all years).

---

- [ ] **Unit 3: `curated.fact_team_fifa_ranking` + quarantine**

**Goal:** Build a curated fact with one row per (team_code, snapshot_date), carrying current FIFA ranking and points.

**Requirements:** R2, R3, R4, R5

**Dependencies:** Unit 1.

**Files:**
- Create: `db/sql/curated/fact_team_fifa_ranking.sql`
- Create: `db/sql/quarantine/unmatched_team_fifa_ranking.sql` *(same convention choice as Unit 2)*
- Modify: `tools/build_duckdb.py` — append to the `FACT_SQL_FILES` and `QUARANTINE_SQL_FILES` lists from Unit 2.
- Test: `tests/db/test_fact_team_fifa_ranking.py`

**Approach:**
- **SQL style: same CTE-first / LEFT-JOIN-then-filter pattern as Unit 2.**
- The fact SQL projects from `raw.fifa_world_ranking_current`, normalizes types, and FK-filters via dim:
  ```sql
  CREATE OR REPLACE TABLE curated.fact_team_fifa_ranking AS
  WITH
  source AS (
      SELECT
          team_code,
          CAST(rank AS INTEGER)                  AS rank,
          CAST(points AS DOUBLE)                 AS points,
          TRY_CAST(previous_points AS DOUBLE)    AS previous_points,
          COALESCE(
              TRY_CAST(ranking_date AS DATE),
              TRY_CAST(fetched_at   AS DATE),
              CURRENT_DATE
          )                                      AS snapshot_date
      FROM raw.fifa_world_ranking_current
  ),
  resolved AS (
      SELECT s.*, d.team_code AS dim_team_code
      FROM source s
      LEFT JOIN curated.dim_team d ON d.team_code = s.team_code
  )
  SELECT
      team_code, rank, points, previous_points, snapshot_date,
      CURRENT_TIMESTAMP AS built_at
  FROM resolved
  WHERE dim_team_code IS NOT NULL;
  ```
  *(Directional sketch.)*
- Grain: one row per `(team_code, snapshot_date)`. Currently single snapshot; future snapshots accumulate by re-running with new data — but since `CREATE OR REPLACE` is the rule, this fact only ever holds the **most recent** snapshot. If a true historical FIFA ranking time series becomes a goal, that lives in a separate `fact_team_fifa_ranking_history` table fed from a different raw source. Document this constraint in the SQL header.
- Quarantine SQL mirrors the fact: same `source` + `resolved` CTEs, opposite `WHERE` (`dim_team_code IS NULL`), adds a `reason` column.

**Patterns to follow:**
- Unit 2's `fact_team_economics.sql`.
- Snapshot/`built_at` columns mirror the `as_of_date` / `CURRENT_DATE` pattern in `fact_team_rating.sql`.

**Test scenarios:**
- *Happy path:* With a fixture `raw.fifa_world_ranking_current` of 5 ranked teams, the fact has 5 rows, `rank` is INTEGER, `points` is DOUBLE, `snapshot_date` is populated.
- *Edge case:* `previous_points` column is missing from the raw parquet (Plan 001 dropped it because the FIFA endpoint did not expose it) — assert the SQL still builds. The implementer adjusts the SELECT to omit the column or wraps it in `TRY_CAST(NULL AS DOUBLE)`.
- *Edge case:* Both `ranking_date` and `fetched_at` are NULL — `snapshot_date` falls back to `CURRENT_DATE` at build time.
- *Error path:* A raw row's `team_code` is not in `dim_team` — it lands in `quarantine.unmatched_team_fifa_ranking` with `reason = 'team_code not in dim_team'`.
- *Integration:* `SELECT d.team_name, f.rank, f.points FROM curated.fact_team_fifa_ranking f JOIN curated.dim_team d USING (team_code) WHERE d.is_wc2026_qualifier ORDER BY f.rank LIMIT 10` returns the top 10 qualifiers by FIFA points.
- *Uniqueness (R10):* `SELECT team_code, COUNT(*) AS n FROM curated.fact_team_fifa_ranking GROUP BY 1 HAVING n > 1` returns zero rows (single-snapshot grain → one row per team).

**Verification:**
- `SELECT COUNT(*) FROM curated.fact_team_fifa_ranking WHERE team_code IN (SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier)` returns 48 (one row per qualifier).
- `SELECT COUNT(DISTINCT snapshot_date) FROM curated.fact_team_fifa_ranking` returns 1.

---

- [ ] **Unit 4: `curated.dim_team_current` denormalized view**

**Goal:** A single read-optimized view that joins `dim_team` with the latest economics row and current FIFA ranking, so model code reads one table for every team feature.

**Requirements:** R5, R6, R9

**Dependencies:** Units 2 and 3.

**Files:**
- Create: `db/sql/curated/dim_team_current.sql`
- Modify: `tools/build_duckdb.py` — register the view SQL in a `VIEW_SQL_FILES` list (introduce one if it does not exist yet), executed after all `FACT_SQL_FILES`. Views must build last because they depend on facts.
- Test: `tests/db/test_dim_team_current.py`

**Approach:**
- Pure view (no materialization). CTE-first style, two LEFT JOINs:
  ```sql
  CREATE OR REPLACE VIEW curated.dim_team_current AS
  WITH
  latest_year AS (
      SELECT MAX(year) AS year
      FROM curated.fact_team_economics
  ),
  latest_economics AS (
      -- One row per team_code = the row with the highest year that has at least one non-null measure.
      SELECT
          e.team_code,
          e.year                  AS economics_year,
          e.gdp_per_capita_usd    AS gdp_per_capita_usd_latest,
          e.population            AS population_latest
      FROM curated.fact_team_economics e
      QUALIFY ROW_NUMBER() OVER (
          PARTITION BY e.team_code
          ORDER BY
              e.year DESC,
              -- prefer rows where at least one measure is non-null
              (CASE WHEN e.gdp_per_capita_usd IS NOT NULL OR e.population IS NOT NULL THEN 0 ELSE 1 END) ASC
      ) = 1
  ),
  current_ranking AS (
      SELECT
          team_code,
          rank          AS fifa_rank,
          points        AS fifa_points,
          snapshot_date AS fifa_snapshot_date
      FROM curated.fact_team_fifa_ranking
  )
  SELECT
      d.team_code,
      d.team_name,
      d.iso2_code,
      d.confederation,
      d.is_wc2026_qualifier,
      e.economics_year,
      e.gdp_per_capita_usd_latest,
      e.population_latest,
      r.fifa_rank,
      r.fifa_points,
      r.fifa_snapshot_date
  FROM curated.dim_team d
  LEFT JOIN latest_economics e ON e.team_code = d.team_code
  LEFT JOIN current_ranking  r ON r.team_code = d.team_code;
  ```
  *(Directional sketch.)*
- The `ROW_NUMBER() … QUALIFY = 1` pattern picks the latest year per team, with a secondary tie-breaker that prefers a non-null row over an all-null row (so Scotland-style all-NULL rows don't shadow earlier years with real data, if the implementer of Plan 001 chose to emit Scotland nulls for every year — depends on the exact shape Plan 001 ships).
- `LEFT JOIN` from `dim_team` means a team without FIFA ranking or economics still appears in the view, with NULL feature columns. Verification surfaces unexpected NULLs separately.
- The view's column naming is explicit: `gdp_per_capita_usd_latest` not `gdp_per_capita_usd`, because the view's grain is per-team-current, not per-team-year. The `_latest` suffix tells the modeler this is a denormalized snapshot.

**Patterns to follow:**
- `db/sql/curated/dim_team.sql` for header docstring style.
- Existing example queries in `db/queries/examples/` for the CTE pipeline shape.

**Test scenarios:**
- *Happy path:* Build the DB against fixtures with 3 teams × 3 years of economics and 3 FIFA ranking rows. Assert `dim_team_current` has 3 rows (one per dim row), each with populated `gdp_per_capita_usd_latest`, `population_latest`, `fifa_rank`.
- *Latest-year selection:* A team has rows for 2023, 2024, 2025 — assert the view shows the 2025 row and `economics_year = 2025`.
- *Non-null tie-break:* A team has a non-null 2024 row and an all-null 2025 row — assert the view shows the 2024 row's values (because the all-null tie-breaker pushes 2025 to rank 2).
- *Edge case (team missing FIFA row):* A dim team not in `fact_team_fifa_ranking` — assert the view emits the team with `fifa_rank = NULL`, `fifa_points = NULL` (LEFT JOIN preserves the dim row).
- *Edge case (team missing economics):* Symmetric — `gdp_per_capita_usd_latest = NULL`, `population_latest = NULL`, but the team still appears.
- *Integration:* `SELECT COUNT(*) FROM curated.dim_team_current` equals `SELECT COUNT(*) FROM curated.dim_team` — the view never adds or drops rows relative to the dim.
- *Uniqueness (R10):* `SELECT team_code, COUNT(*) AS n FROM curated.dim_team_current GROUP BY 1 HAVING n > 1` returns zero rows.

**Verification:**
- Row count of view equals row count of `curated.dim_team`.
- For WC2026 qualifiers: `fifa_rank IS NOT NULL` AND `fifa_points IS NOT NULL` for all 48 rows.
- For WC2026 qualifiers: `economics_year >= 2025` for at least 47 of 48 (Scotland exception documented).

---

- [ ] **Unit 5: Verification, schema doc, example query**

**Goal:** Wire dim-integrity checks into `verify_duckdb.py`, document the new artifacts in `db/SCHEMA.md`, and ship one example query that proves the model-facing read path.

**Requirements:** R7, R8

**Dependencies:** Units 1–4.

**Files:**
- Modify: `db/sql/verify_duckdb.py` — add the new facts and view to its row-count and orphan-check lists.
- Modify: `db/SCHEMA.md` — add `fact_team_economics`, `fact_team_fifa_ranking`, and `dim_team_current` sections under the curated heading; document grain, columns, source tables, and FK guarantee.
- Create: `db/queries/examples/team_features_for_modeling.sql` — single-table read from `dim_team_current` filtered to WC2026 qualifiers, ordered by FIFA rank.
- Test: extend `tests/db/test_verify_duckdb.py` if it exists.

**Approach:**
- In `verify_duckdb.py`, add checks of the same shape used for `fact_team_rating`:
  - Row count > 0 for both new facts.
  - **`fact_team_economics`:** all 48 WC2026 qualifiers present **for the latest year** (`year = (SELECT MAX(year) FROM curated.fact_team_economics)`). Earlier-year gaps are logged but not failed — see Key Technical Decisions.
  - **`fact_team_fifa_ranking`:** all 48 WC2026 qualifiers present (single snapshot, so the rule is unconditional).
  - **`dim_team_current`:** row count equals `dim_team` row count; for every WC2026 qualifier, both `fifa_points` and `gdp_per_capita_usd_latest` are non-null (Scotland exception explicitly tolerated for the economics column).
  - **Uniqueness (R10):** zero duplicate keys in any of the three new objects (`fact_team_economics` on `(team_code, year)`, `fact_team_fifa_ranking` on `team_code`, `dim_team_current` on `team_code`). Each check is one `GROUP BY … HAVING COUNT(*) > 1` SQL — fails fast naming the offender.
  - **Last-5-years coverage (R11):** for every WC2026 qualifier, `fact_team_economics` contains a row for each of the last 5 years (`MAX(year) - 4` through `MAX(year)`). The verify script's check is the LEFT-JOIN-against-CROSS-JOIN query from Unit 2; non-zero result fails the build with a table of missing `(team_code, year)` pairs.
  - Quarantine tables exist (may be empty); non-empty quarantine for **any** WC2026 qualifier (any year) raises — this catches FK breakage early, separately from the latest-year coverage rule.
- The example query is a one-line read from the denormalized view:
  ```sql
  -- Single-table read of every team feature for the 48 WC2026 qualifiers.
  -- Joins live in the view; modelers do not see them.
  SELECT
      team_code,
      team_name,
      confederation,
      fifa_rank,
      fifa_points,
      gdp_per_capita_usd_latest,
      population_latest,
      economics_year
  FROM curated.dim_team_current
  WHERE is_wc2026_qualifier
  ORDER BY fifa_rank NULLS LAST;
  ```

**Patterns to follow:**
- `db/sql/verify_duckdb.py` existing structure.
- `db/queries/examples/*.sql` — terse top-of-file comment, single statement, runnable as-is.

**Test scenarios:**
- *Happy path:* Run `verify_duckdb.py` against a freshly built DB; assert it exits 0 and prints the new facts' and view's row counts.
- *Error path (fact orphan):* Drop a WC2026 qualifier from `dim_team` (in-test mutation) so the orphan check fires; assert the script exits non-zero with a message naming the missing team_code.
- *Error path (view coverage):* Delete the FIFA ranking row for a WC2026 qualifier so the view emits NULL `fifa_points` for that team; assert the view-coverage check fails with a clear message.
- *Error path (uniqueness):* Insert a duplicate `(team_code, year)` row directly into `curated.fact_team_economics`; assert verify exits non-zero naming the offending key.
- *Error path (5-year coverage):* Delete all 2021 rows for one WC2026 qualifier; assert verify exits non-zero listing the missing `(team_code, 2021)` pair.
- *Smoke:* Execute the example query against the built DB and assert it returns 48 rows with non-null `fifa_rank` for all of them.

**Verification:**
- `python3 db/sql/verify_duckdb.py` exits 0 against a healthy build.
- `db/SCHEMA.md` has new entries for both facts and the view under the curated section.
- The example query returns 48 rows when run via `duckdb data/wc2026.duckdb`.

## System-Wide Impact

- **Interaction graph:** `tools/build_duckdb.py` gains three new raw tables, two new fact SQL files, and one view SQL file. The build's phase order becomes `raw → curated.dim_* → curated.fact_* → curated.<view>_*`. No change to the matching layer (`db/sql/match_sources_to_masters.py`) because these sources do not need matching.
- **Error propagation:** Missing parquets fail fast in `load_raw`. Missing `team_code` in `dim_team` quarantines the row. WC2026-qualifier orphans in quarantine, or NULL feature columns in the view for qualifiers, cause `verify_duckdb.py` to exit non-zero.
- **State lifecycle risks:** `CREATE OR REPLACE` everywhere (TABLE for facts, VIEW for `dim_team_current`). No accumulation logic — re-running the build is safe. The FIFA ranking fact only ever holds the latest snapshot, which is intentional and documented.
- **API surface parity:** Models reading team features should standardize on `curated.dim_team_current`. The underlying facts remain available for any caller needing the time series (economics) or snapshot grain (ranking).
- **Integration coverage:** Unit 5's example query is the integration probe; it reads from the view and indirectly touches all three new tables plus `dim_team`.
- **Unchanged invariants:** `curated.dim_team` is unchanged. `db/masters/teams.csv` is unchanged. The existing `fact_team_rating` and `fact_player_xg` builds are untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Plan 001's parquets ship with column names different from what the SQL expects. | Unit 2 and Unit 3 each `TRY_CAST` and use `COALESCE` for date fields; the SQL is tolerant. Tests use real-shaped fixtures, not schema-frozen mocks. |
| World Bank coverage gaps (e.g., USSR-era successor states pre-1991) leave Scotland-style NULL rows the modeler does not expect. | `fact_team_economics` keeps NULL rows by design; this is documented in `db/SCHEMA.md` and the verify script's output. |
| `FACT_SQL_FILES` / `QUARANTINE_SQL_FILES` lists do not yet exist in `tools/build_duckdb.py` and need to be introduced. | Unit 2 introduces them with the same shape as `DIM_SQL_FILES`. Small refactor; covered by the existing build test. |
| FIFA fact only holds the latest snapshot; analyst expects history. | Documented in the SQL header and `db/SCHEMA.md` (`grain: latest snapshot only`). History is explicitly deferred to a future plan. |

## Documentation / Operational Notes

- `db/SCHEMA.md` gets two new fact entries with grain, columns, source raw tables, and FK guarantee.
- No new env vars, no new dependencies.
- The build remains a single command: `python3 tools/build_duckdb.py`.

## Sources & References

- **Origin document:** [docs/plans/2026-05-14-001-feat-country-context-features-plan.md](2026-05-14-001-feat-country-context-features-plan.md) — produces the three parquets this plan consumes.
- Related code:
  - `tools/build_duckdb.py` — build entry point.
  - `db/sql/curated/dim_team.sql` — dim being matched against.
  - `db/sql/curated/fact_team_rating.sql` — fact-building precedent.
  - `db/sql/verify_duckdb.py` — verification harness.
  - `db/SCHEMA.md` — contract doc.
- Related queries: `db/queries/examples/` directory for analyst-facing SQL.
