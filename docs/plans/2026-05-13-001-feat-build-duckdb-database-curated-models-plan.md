---
title: "feat: Build DuckDB Database with Master-Data-Management for WC2026 Analytics"
type: feat
status: completed
date: 2026-05-13
---

# feat: Build DuckDB Database with Master-Data-Management for WC2026 Analytics

## Overview

Build a DuckDB analytics database at `data/wc2026.duckdb` following master-data-management (MDM) principles. **Authoritative masters drive the dim tables; raw stats are matched *to* the dims one-way.** No dim entity is ever derived by unioning fact sources.

The pipeline has six clear stages:

1. **Design** the data model on paper before any DDL is written.
2. **Masters** — pull and curate the authoritative source for each dim: rosters for players, FIFA list for teams, hand-curated for tournaments, scanned for models. Committed CSVs at `db/masters/*.csv` with stable surrogate keys.
3. **Raw layer** — load every in-scope parquet from `data/derived/` into `raw.*` tables in DuckDB (1:1 mirrors).
4. **Dims + matching** — build `curated.dim_*` from the masters; align every raw stats row to a `player_id` via tiered matching; quarantine unmatched rows.
5. **Facts** — build `curated.fact_*` from matched-source intermediates joined to dims.
6. **Verify + test DuckDB** — automated sanity assertions, a documented set of example analytical queries, and a README walkthrough so the user can `duckdb data/wc2026.duckdb` and start exploring the moment the build finishes.

Visualization is **explicitly deferred** to a separate plan that will sit on top of this database.

## Problem Frame

The project produces ~25 parquet files in `data/derived/` (team ratings, player xG from StatsBomb and Understat, squads, market snapshots). Every consumer reads these parquets ad-hoc with pandas, reinventing normalization (FIFA codes, name matching, joins) inline. There is no unified query layer, no canonical player identity, no curated data model.

We want a DuckDB database where:
- **Dims are authoritative and stable.** A player's `player_id` is assigned once and never changes across rebuilds, roster refreshes, or new source additions.
- **Facts are clean.** Every fact row references its dims via surrogate keys, never names.
- **Matching is a load-time concern, not a query-time concern.** Analytical queries just JOIN on resolved IDs.
- **Unmatched data is visible, not silently lost.** A `quarantine.*` schema surfaces every stats row that failed to match a master, so data-quality issues are inspectable.

After this plan, the user can run `duckdb data/wc2026.duckdb` and execute analytical queries like "top scorers by blended xG", "model agreement matrix per team", "players in WC2026 squads with no club xG data" — directly, with no Python glue.

## Requirements Trace

- R1. `python3 tools/build_duckdb.py` produces `data/wc2026.duckdb` end-to-end from the masters in `db/masters/` and the parquets in `data/derived/`.
- R2. The build is idempotent — re-running produces an identical DB with no duplicate rows, no orphan tables, and identical `player_id` assignments.
- R3. Authoritative masters live as committed CSVs at `db/masters/`: `players.csv`, `teams.csv`, `tournaments.csv`, `models.csv`. They survive DB rebuilds and clean clones.
- R4. Player surrogate keys (`P######`) are stable across builds, across master refreshes (e.g., when finalized WC2026 rosters drop ~Jun 4), and across re-runs after manual edits. A player who exists in master version N must keep the same ID in version N+1 if they're still in the roster.
- R5. The curated layer exists in the `curated.*` schema and includes at minimum: `dim_player`, `dim_team`, `dim_tournament`, `dim_model`, `fact_player_xg`, `fact_team_rating`. Each is documented in `db/SCHEMA.md`.
- R6. The matching layer (`tools/match_sources_to_masters.py`) resolves a `player_id` for every raw stats row where possible. Unmatched rows land in `quarantine.unmatched_<source>` tables with a `reason` column.
- R7. The build pipeline logs row counts per layer (raw, dim, staging, quarantine, fact) so data drift is visible.
- R8. `tools/verify_duckdb.py` runs sanity assertions and exits non-zero on failure.
- R9. `db/queries/examples/*.sql` contains at least 5 analytical example queries that the user can run interactively to "test DuckDB" — top scorers, model agreement matrix, attack-vs-defense scatter source data, squad coverage gaps, and at least one quarantine-inspection query.
- R10. `db/README.md` documents the build command, masters refresh workflow, schema overview, and the example queries, so a new contributor can use the DB without re-reading this plan.

## Scope Boundaries

- **In scope:** masters for players/teams/tournaments/models, raw layer for all canonically-shared parquets, curated dim/fact layer, matching pipeline with quarantine, verify script, schema doc, DB README, example queries.
- **Out of scope:** Any visualization (Graphene, Streamlit, etc.), market-data snapshots (Kalshi/Polymarket CSVs — separate plan, different schema cadence), model comparison outputs (`results/comparisons/`), live in-tournament data refresh (per `MEMORY.md` → `wc2026_live_pipeline_plan.md`), and `fact_match` / `fact_prediction` (deferred to a follow-up).
- Not modifying any pipeline script that produces a parquet. Parquets and rosters are read-only inputs to this work.
- Not building incremental loads or staging migrations. The DB is rebuilt from scratch on every run; masters are the only persistent state.

### Deferred to Separate Tasks

- **Visualization tool** on top of this DB: separate plan once the curated layer is stable.
- **Live in-tournament refresh** (Sofascore / API-Football pull from ~Jun 4): per `MEMORY.md`; the dim_player master will need a refresh trigger at that point, but the refresh tool is built in this plan and reusable.
- **Market snapshots** (`kalshi_snapshot_*.csv`, `polymarket_snapshot_*.csv`) → `fact_market_price`: separate plan once schema stabilizes.
- **Model predictions** (`results/<model>/<date>/predictions.csv`) → `fact_prediction`: separate plan.
- **Match-level data** (`fact_match` from FIFA fixture list) — straightforward to add, but the existing parquets don't cover this so it's a separate ingestion.

## Context & Research

### Relevant Code and Patterns

- `tools/pull_wc2026_squads.py` and `tools/pull_wc2026_final_squads.py` — existing roster scrapers. The player master CSV is derived from their JSON outputs in `data/raw/squads/`.
- `tools/weekly_pull.py` — contains `NAME_TO_FIFA3` and `ISO2_TO_FIFA3` dicts; the team master CSV is derived from these.
- `tools/build_squad_xg_ratings.py` — pattern for "read multiple inputs, derive an output" scripts; tone and structure for `tools/build_duckdb.py`.
- `ensemble_model.py` and `wc2022_xg_backtest.py` — current pandas consumers; what they re-derive inline is what the curated layer should pre-bake.
- `data/raw/squads/wc2026_squads_confirmed.json` — current best WC2026 roster data (already pulled).
- `results/_template/MODEL.md` and `results/<model>/MODEL.md` — model master CSV is derived by scanning these.
- `rapidfuzz` is already a project dependency (per `ensemble_model.py` imports).

### Institutional Learnings

- `docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md` — model-disagreement views drive betting strategy; `fact_team_rating` keyed on `(team_code, model_id)` makes this a one-line GROUP BY.
- `MEMORY.md` → `feedback_player_identity_registry.md` — the MDM principle (this plan implements it).
- `MEMORY.md` → `wc2026_live_pipeline_plan.md` — final rosters land ~Jun 4; the master-refresh tool built here is the mechanism for picking that up without ID churn.
- `MEMORY.md` → `wc2022_backtest_learnings.md` — Golden Zone rule (3-model agreement) is the headline derived metric; not in this plan but the data shape is designed to make it trivial.

### External References

- DuckDB Python API: `duckdb.connect(path)`, `con.execute(sql)`, `con.read_csv(path)`, built-in `read_parquet()`.
- DuckDB schemas (namespaces): `CREATE SCHEMA IF NOT EXISTS <name>` — using `raw`, `curated`, `staging`, `quarantine` for separation.
- DuckDB fuzzy-string built-ins: `jaro_winkler_similarity()`, `levenshtein()`, `damerau_levenshtein()`. Useful for matching, but `rapidfuzz.token_set_ratio` (in Python) handles "long name vs short name" better, so primary fuzzy logic stays in Python.

## Key Technical Decisions

- **Master-data-management throughout.** Every dim has an authoritative master at `db/masters/<entity>.csv`. Facts reference dims via surrogate keys (`player_id`) or canonical natural keys (`team_code`). No fact-table data ever extends a master.
- **DuckDB file location: `data/wc2026.duckdb`.** Gitignored; rebuildable from masters + parquets in seconds.
- **Build tooling: Python `duckdb` package** via `tools/build_duckdb.py`. Hybrid model: inline SQL for the raw layer, `.sql` files in `db/sql/curated/` for the dim/fact layer, Python for the matching layer (where `rapidfuzz` is needed).
- **Schemas in DuckDB: `raw`, `curated`, `staging`, `quarantine`.** Four-namespace separation makes queries self-documenting (`SELECT * FROM quarantine.unmatched_statsbomb_players` is obvious).
- **Idempotency via `CREATE OR REPLACE TABLE` for everything in DuckDB.** The DB is a derived artifact. The masters (committed CSVs) are the only persistent state.
- **Surrogate key persistence.** `db/masters/players.csv` carries the `player_id` column. The roster-refresh tool reads existing IDs, matches incoming roster rows to them, preserves IDs for matches, and assigns new `P######` only for genuine new players. IDs are never reassigned, never reused.
- **Player ID format: `P######` zero-padded sequential** (e.g., `P000001`). Stable, sortable, greppable.
- **Player matching key: `(normalized_name, country_code, birth_year)`.** Birth year (from roster DOB) is the killer disambiguator — it makes "Carlos Ruiz, GUA, 1979" unambiguously distinct from "Carlos Ruiz, MEX, 1989". Fall back to fuzzy name match (rapidfuzz token_set_ratio ≥90) only when DOB is missing on the stats side.
- **Wide `dim_player`, source-name columns inline.** Columns include `statsbomb_name`, `understat_name`, and any future source. Populated during matching; persist on the master. New source = new column, no schema migration to fact tables.
- **Matching is one-way and load-time only.** Raw stats → match to existing dim_player → matched intermediate → fact. Unmatched stats rows go to `quarantine.*`, never into the master.
- **Quarantine, not silent drop.** Every unmatched row appears in `quarantine.unmatched_<source>` with `reason` (`no_match` / `ambiguous_match` / `missing_birth_year` / etc.) and the original raw row contents. Build doesn't fail on quarantine rows; verify script logs the counts.
- **Master refresh is a separate tool.** `tools/refresh_player_master.py` takes a new roster JSON (e.g., the post-Jun-4 final squads) and updates `db/masters/players.csv` with ID preservation. Build script doesn't refresh masters — it just consumes them. This separates "data acquisition" from "data loading."
- **Team identity uses FIFA 3-letter codes** as the natural key — no surrogate. Codes are already canonical per `DEVELOPMENT.md` line 238 and `tools/weekly_pull.py:NAME_TO_FIFA3`.
- **Tournament identity uses short string IDs** (`wc2026`, `wc2022`, `euro2024`, `copa2024`). Small enumeration; hand-curated.
- **Model identity uses slug from directory name** in `results/<model>/`. Auto-derived; matches existing project convention.

## Open Questions

### Resolved During Planning

- *Where does dim_player come from?* The roster master (`db/masters/players.csv`), not from a stats union.
- *How are player IDs preserved across master refreshes?* The refresh tool matches incoming roster rows against existing master rows on `(normalized_name, country_code, birth_year)` and preserves IDs.
- *What happens to unmatched stats rows?* Quarantine, not drop. Surfaced by verify script.
- *Is `dim_player` wide or long?* Wide. Source-specific name columns inline.
- *Build script vs. dbt or SQLMesh?* Pure Python + DuckDB. No framework.
- *Does final WC2026 roster need to be available before this plan can land?* No. v1 uses current best squad data (`data/raw/squads/wc2026_squads_confirmed.json`). Final rosters trigger a master-refresh after Jun 4 using the same tool.

### Deferred to Implementation

- **Exact roster JSON schema** — depends on `tools/pull_wc2026_squads.py` output format; Unit 2 confirms when building the master.
- **DOB completeness across roster sources** — Wikipedia squad pages typically have DOB; if any squad is missing DOB, we fall back to `(normalized_name, country_code)` for those players with a stricter fuzzy threshold. Unit 4 confirms with real data.
- **Match score thresholds** — `rapidfuzz.token_set_ratio ≥90` is the planned threshold; final tuning happens in Unit 4 with real distributions.
- **Whether to include historical-tournament rosters** (WC2022, Euro2024, Copa2024) — the stats parquets cover these tournaments. If we want `fact_player_xg` to include historical players who aren't in WC2026 squads, we need separate masters. Unit 1 decides: most likely **yes, but quarantine the unmatched historical players for v1** — better than silently extending masters from facts.
- **Whether `fact_match` (the WC2026 fixture list) is in v1** — likely no, it requires a separate fixture pull. Schema doc lists it as a near-future addition.

## Output Structure

```
data/
└── wc2026.duckdb                       (generated; gitignored)

db/                                     (new top-level dir)
├── README.md                           (build, query, refresh workflows)
├── SCHEMA.md                           (data-model design doc; committed BEFORE build)
├── masters/                            (authoritative committed CSVs)
│   ├── players.csv                     (master player roster; player_id assigned here)
│   ├── teams.csv                       (FIFA 211; derived from NAME_TO_FIFA3)
│   ├── tournaments.csv                 (hand-curated enum)
│   └── models.csv                      (scanned from results/<model>/MODEL.md)
├── queries/
│   └── examples/                       (analytical query starters for "test DuckDB")
│       ├── top_scorers_blended_xg.sql
│       ├── model_agreement_matrix.sql
│       ├── attack_vs_defense_per_team.sql
│       ├── squad_coverage_gaps.sql
│       └── inspect_quarantine.sql
└── sql/
    └── curated/
        ├── dim_player.sql
        ├── dim_team.sql
        ├── dim_tournament.sql
        ├── dim_model.sql
        ├── fact_player_xg.sql
        └── fact_team_rating.sql

tools/                                  (existing dir)
├── build_duckdb.py                     (new; orchestrates all 4 in-DB layers)
├── refresh_player_master.py            (new; master refresh, ID preservation)
├── match_sources_to_masters.py         (new; Python matching with rapidfuzz)
├── verify_duckdb.py                    (new; sanity assertions)
├── inspect_parquets.py                 (new; small utility for Unit 1)
└── lib/
    └── player_normalize.py             (new; shared name-normalization function)

.gitignore                              (updated: data/*.duckdb, data/*.duckdb-wal)
```

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.*

```
                       ┌─────────────────── MASTERS (committed CSV) ───────────────────┐
                       │                                                                 │
   roster JSON ─┐      │  db/masters/players.csv     (player_id, dob, country, names)   │
   FIFA list ───┼──→   │  db/masters/teams.csv       (team_code, name, confederation)   │
   hand edit ───┤      │  db/masters/tournaments.csv (tournament_id, name, dates)       │
   results/ ────┘      │  db/masters/models.csv      (model_id, methodology_path)       │
                       └────────────────────────┬───────────────────────────────────────┘
                                                │
                                                ▼  CREATE OR REPLACE TABLE ... AS SELECT * FROM read_csv(...)
   data/derived/                ┌──────── DuckDB: curated.dim_* ────────┐
   *.parquet ─→ raw.*           │  curated.dim_player                   │
                  │              │  curated.dim_team                     │
                  │              │  curated.dim_tournament               │
                  │              │  curated.dim_model                    │
                  │              └────────────────┬──────────────────────┘
                  │                               │
                  │                               ▼
                  │   ┌──── tools/match_sources_to_masters.py ────────────┐
                  │   │  For each raw stats source:                        │
                  └──→│   1. normalize name; lookup (norm_name, country,   │
                      │      birth_year) in dim_player                     │
                      │   2. tier 1 exact → tier 2 fuzzy ≥90 → quarantine  │
                      │  Outputs: staging.matched_<source>                 │
                      │           quarantine.unmatched_<source>            │
                      └────────────────┬──────────────────────┬────────────┘
                                       │                      │
                                       ▼                      ▼
                              ┌── curated.fact_* ──┐   ┌── quarantine.* ──┐
                              │  fact_player_xg    │   │  unmatched_*     │
                              │  fact_team_rating  │   │  (review queue)  │
                              └────────────────────┘   └──────────────────┘
                                       │
                                       ▼
                       tools/verify_duckdb.py  (assertions, row counts, FK integrity)
                                       │
                                       ▼
                       duckdb data/wc2026.duckdb  +  db/queries/examples/*.sql
                                       │
                                       ▼
                                    USER TESTS
```

Representative master shape (one row):

```
db/masters/players.csv:
player_id,display_name,normalized_name,country_code,birth_date,birth_year,position,current_club,statsbomb_name,understat_name,is_active,first_seen_at,last_updated_at
P000001,Lionel Messi,lionel messi,ARG,1987-06-24,1987,FW,Inter Miami CF,Lionel Andrés Messi Cuccittini,Lionel Messi,true,2026-05-13,2026-05-13
```

Representative matching tier (Python pseudo-logic):

```python
# Inside match_sources_to_masters.py — directional, not literal code
def resolve_player_id(raw_row, dim_player_df):
    norm = normalize(raw_row.source_name)
    by = raw_row.birth_year  # None if source doesn't carry DOB
    cc = raw_row.country_code  # None if source doesn't carry country

    # Tier 1: exact on (normalized_name, country_code, birth_year) — strongest signal
    if by and cc:
        hits = dim_player_df[
            (dim_player_df.normalized_name == norm)
            & (dim_player_df.country_code == cc)
            & (dim_player_df.birth_year == by)
        ]
        if len(hits) == 1: return hits.iloc[0].player_id, "tier1_exact_with_dob"

    # Tier 2: exact on (normalized_name, country_code) — strong but no DOB
    if cc:
        hits = dim_player_df[
            (dim_player_df.normalized_name == norm)
            & (dim_player_df.country_code == cc)
        ]
        if len(hits) == 1: return hits.iloc[0].player_id, "tier2_exact_no_dob"

    # Tier 3: fuzzy ≥90 token_set_ratio + at least one shared context field
    candidates = rapidfuzz.process.extract(norm, dim_player_df.normalized_name,
                                            scorer=fuzz.token_set_ratio,
                                            score_cutoff=90)
    candidates_with_context = [c for c in candidates if shares_country_or_club(c, raw_row)]
    if len(candidates_with_context) == 1:
        return candidates_with_context[0].player_id, "tier3_fuzzy"

    # No match: quarantine
    return None, "no_match" if not candidates else f"ambiguous_{len(candidates_with_context)}"
```

## Implementation Units

- [ ] **Unit 1: Schema design + parquet/master inventory (docs only)**

**Goal:** Capture the schema of every in-scope parquet AND every existing roster source. Write the full target data model into `db/SCHEMA.md` before any DDL or master CSV is written.

**Requirements:** R5 is anchored here; design source for R3–R7.

**Dependencies:** None.

**Files:**
- Create: `db/SCHEMA.md` — full data-model design doc.
- Create: `tools/inspect_parquets.py` — prints columns + dtypes + 3 sample rows + row count for every parquet in `data/derived/`, plus a `--player-names` mode that samples player-name fields across the player parquets.

**Approach:**
- Run the inspect script; capture output as the foundation for SCHEMA.md.
- Inspect `data/raw/squads/wc2026_squads_confirmed.json` (and the squad JSON file structure) to confirm the roster source has DOB, country, position, club.
- Write `db/SCHEMA.md` with these sections:
  - **Masters:** one section per master CSV, listing every column with type, description, and source provenance (where each value comes from — roster JSON field path, dict key, etc.). `players.csv` is the longest section.
  - **Raw layer:** one row per in-scope parquet → target `raw.<name>` table, column lists verbatim from inspect output.
  - **Curated dims:** one section per dim, listing columns, primary key, and the master it sources from.
  - **Matching contract:** the tiered matching algorithm, scoring thresholds, what goes to quarantine and why.
  - **Curated facts:** one section per fact, listing columns, grain (one row per what), the raw sources, and the dim FKs.
  - **Quarantine schema:** the structure of `quarantine.unmatched_<source>` tables and the `reason` enum.
  - **Identity decisions:** team_code (FIFA), player_id (P######), tournament_id (slug), model_id (dir slug).
  - **Out-of-scope tables:** market snapshots, comparison outputs, fact_match — explicitly named so reviewers know what's deferred.
- No DDL, no master CSV content, no Python beyond the inspect script.

**Execution note:** Design first. Resist writing `CREATE TABLE` or filling `players.csv` — those happen in Unit 2.

**Patterns to follow:**
- `tools/build_squad_xg_ratings.py` for the inspect script's tone.
- Plan style in `docs/plans/2026-05-05-002-feat-wc2026-prediction-report-plan.md` for the schema doc's section structure.

**Test scenarios:**
- Happy path: `python3 tools/inspect_parquets.py` outputs a deterministic inventory.
- Happy path: `python3 tools/inspect_parquets.py --player-names` samples 20 names from each player parquet and prints them side-by-side, surfacing naming convention differences.
- Happy path: every parquet listed in `DEVELOPMENT.md` lines 14–23 is covered in SCHEMA.md.
- Happy path: SCHEMA.md's masters section names every column with type and source provenance.
- Happy path: SCHEMA.md's matching contract is unambiguous — a reader could implement it without further questions.
- Edge case: inspect script handles parquets with non-ASCII columns or values.

**Verification:**
- A reviewer reads `db/SCHEMA.md` and can answer: "What columns does `db/masters/players.csv` have, where does each come from, and how does a new Understat row get a `player_id`?" without opening any other file.

- [ ] **Unit 2: Build the four masters (committed CSVs)**

**Goal:** Produce `db/masters/players.csv`, `db/masters/teams.csv`, `db/masters/tournaments.csv`, `db/masters/models.csv` with stable surrogate keys. These are the system of record.

**Requirements:** R3, R4.

**Dependencies:** Unit 1 (SCHEMA.md defines master columns and source mappings).

**Files:**
- Create: `tools/lib/player_normalize.py` — shared `normalize(name)` and `normalize_country(name) → FIFA3` functions.
- Create: `tools/refresh_player_master.py` — takes a roster JSON (default: `data/raw/squads/wc2026_squads_confirmed.json`), updates `db/masters/players.csv` with ID preservation. Callable standalone; also invoked by future re-runs after Jun 4 roster drops.
- Create: `db/masters/players.csv` — bootstrap by running `refresh_player_master.py` for the first time, then commit after manual review.
- Create: `db/masters/teams.csv` — small generator script or one-shot derivation from `tools/weekly_pull.py:NAME_TO_FIFA3` + a hand-added `confederation` column. Commit the resulting CSV.
- Create: `db/masters/tournaments.csv` — hand-curated, 4–6 rows (wc2026, wc2022, euro2024, copa2024, plus any historical relevant ones).
- Create: `db/masters/models.csv` — one-shot derivation from scanning `results/*/MODEL.md` (looks for the methodology dir name as `model_id`). Commit.

**Approach:**
- `tools/lib/player_normalize.py`: `normalize(name)` does NFKD strip → lowercase → collapse whitespace → strip non-alphanumeric. Pure function, importable.
- `tools/refresh_player_master.py`:
  - `argparse`: `--roster-path`, `--master-path` (default `db/masters/players.csv`), `--dry-run`.
  - Load existing master (if file exists; empty DataFrame on first run).
  - Load roster JSON; flatten to (country_code, display_name, dob, position, club) rows.
  - For each roster row, match against existing master on `(normalized_name, country_code, birth_year)`. If match → update attributes (club, position), preserve `player_id`. If no match → assign new `P######` starting from `max(existing) + 1`.
  - Mark master rows whose player no longer appears in any roster as `is_active = false`. Never delete.
  - Write master CSV sorted by `player_id` for stable diffs.
  - Print summary: `[master] N total, M new this run, K marked inactive`.
- First-run bootstrap is intentionally permissive: every roster player gets a new ID. Manual review of the first `players.csv` before committing — look for accent-collision duplicates (`Müller` vs `Muller`), nickname duplicates (`Mo Salah` vs `Mohamed Salah`) — and merge by hand. The first commit is the most important review pass.
- Team master: small one-shot script that emits `teams.csv` from the FIFA dicts plus a confederation column. Could be inlined into the build script as a Python helper if it's too small for its own file. Decided by implementer.
- Tournament + model masters: hand-curated or one-shot derived. Tiny tables.

**Patterns to follow:**
- `tools/build_squad_xg_ratings.py` argparse + stdout logging pattern.
- The existing `data/raw/sofascore/understat_id_map.json` shows the project's appetite for committed source-mapping files; `players.csv` is the same pattern.

**Test scenarios:**
- Happy path: `python3 tools/refresh_player_master.py` on a fresh repo produces `players.csv` with one row per distinct (player, country) in the roster, sequential `P######` IDs.
- Happy path (idempotency): running the script twice with no new roster data produces identical row counts and identical `player_id` values; only `last_updated_at` may change.
- Happy path: simulating a roster refresh — add a fictional new player to the roster JSON, re-run → exactly one new row with the next sequential ID; all existing IDs unchanged.
- Happy path: simulating a player drop — remove a player from the roster JSON, re-run → the existing row stays in `players.csv` with `is_active = false`; ID preserved.
- Happy path: `teams.csv` has 211 rows (FIFA member associations) plus a `confederation` column; `tournaments.csv` has 4–6 rows; `models.csv` has one row per directory under `results/`.
- Edge case: roster JSON missing DOB for some players → row is created with `birth_date = NULL`; flagged for review in script summary.
- Edge case: master CSV is hand-edited between runs → script accepts the edits without trying to overwrite them.
- Edge case: two roster rows have identical `(normalized_name, country_code, birth_year)` → script logs a clear warning, processes the first row only.

**Verification:**
- `db/masters/players.csv` exists, is committable, and has reviewable content (sorted by `player_id`, valid CSV).
- A second run of `refresh_player_master.py` produces zero diff in `players.csv` (or only `last_updated_at` diffs, depending on implementation).
- All four master CSVs are committed before Unit 3 starts.

- [ ] **Unit 3: Build the DuckDB raw layer + dims**

**Goal:** Create `data/wc2026.duckdb`, load every in-scope parquet into `raw.*`, and load every master into `curated.dim_*`. Half the schema is in place after this unit.

**Requirements:** R1 (partial — command exists and produces the file), R2 (idempotency), R5 (dims exist), R7 (row count logging).

**Dependencies:** Unit 1 (SCHEMA.md defines raw + dim columns), Unit 2 (master CSVs exist).

**Files:**
- Create: `tools/build_duckdb.py` v1 — orchestrates raw load + dim build (matching and facts arrive in later units).
- Create: `db/sql/curated/dim_player.sql`, `dim_team.sql`, `dim_tournament.sql`, `dim_model.sql` — each is a single `CREATE OR REPLACE TABLE curated.<name> AS SELECT * FROM read_csv('db/masters/<name>.csv', ...)`.
- Update: `.gitignore` — add `data/*.duckdb` and `data/*.duckdb-wal`.

**Approach:**
- `tools/build_duckdb.py`:
  - `argparse`: `--db-path` (default `data/wc2026.duckdb`), `--data-dir` (default `data/derived`), `--masters-dir` (default `db/masters`).
  - Connect to DuckDB. `CREATE SCHEMA IF NOT EXISTS raw`, `curated`, `staging`, `quarantine`.
  - **Raw phase:** hardcoded mapping `(parquet_filename, table_name)` near the top of the script; for each pair, `CREATE OR REPLACE TABLE raw.<name> AS SELECT * FROM read_parquet(?)`. Log `[raw] <name>: <count> rows` after each.
  - **Dim phase:** iterate `db/sql/curated/dim_*.sql` in alphabetical order (dims have no inter-dependencies). For each, `con.execute(file_contents)`. Log `[dim] <name>: <count> rows`.
  - Exit 0 on success. Clear error message on missing parquet or missing master file.
- Each `db/sql/curated/dim_*.sql` file:
  - Starts with a `-- ` comment block: purpose, primary key, source CSV.
  - Single statement: `CREATE OR REPLACE TABLE curated.dim_<name> AS SELECT [columns with types] FROM read_csv('db/masters/<name>.csv', delim=',', header=true, columns={...})`.
  - Explicit column types (don't rely on DuckDB inference for committed CSVs — type annotations make the contract visible).

**Patterns to follow:**
- `tools/build_squad_xg_ratings.py` argparse and logging.
- DuckDB's `read_csv(path, columns={'col1': 'VARCHAR', ...})` for explicit-type CSV reads.

**Test scenarios:**
- Happy path: `python3 tools/build_duckdb.py` produces `data/wc2026.duckdb` with all `raw.*` and `curated.dim_*` tables populated. Row counts in logs match pandas reads of the parquets and CSVs.
- Happy path (idempotency): running twice produces identical row counts; no orphan tables, no errors.
- Happy path: `duckdb data/wc2026.duckdb -c "SHOW TABLES FROM raw"` and `"SHOW TABLES FROM curated"` return the expected tables.
- Edge case: a parquet is missing → script exits non-zero with a clear error.
- Edge case: a master CSV is missing → same.
- Edge case: an existing DB with a leftover orphan table (manually created) — `CREATE OR REPLACE` doesn't remove the orphan but the script doesn't fail. Document in README: orphans require manual drop or a fresh DB file.
- Edge case: DuckDB WAL file from an interrupted run — the next successful run cleans it up. (DuckDB handles WAL replay on connect.)

**Verification:**
- All raw tables and all dim tables exist.
- `SELECT COUNT(*) FROM curated.dim_player` matches `len(players.csv)`.
- A reviewer can run `duckdb data/wc2026.duckdb -c "SELECT * FROM curated.dim_player LIMIT 5"` and see real player data with valid `player_id`s.

- [ ] **Unit 4: Build the matching pipeline + quarantine**

**Goal:** For every raw stats row that references a player, resolve `player_id` via tiered matching. Outputs go to `staging.matched_<source>` (rows that joined cleanly) and `quarantine.unmatched_<source>` (rows that didn't). This unit is the algorithmic core of the build.

**Requirements:** R6, R7 (matching counts in logs).

**Dependencies:** Unit 3 (raw layer and dim_player must exist in DuckDB).

**Files:**
- Create: `tools/match_sources_to_masters.py` — Python script with the matching tiers.
- Update: `tools/build_duckdb.py` — invoke `match_sources_to_masters.main()` after the dim phase.

**Approach:**
- `tools/match_sources_to_masters.py`:
  - `argparse`: `--db-path`, `--quarantine-only` (for re-running just the quarantine inspection without rebuilding the matched tables).
  - Connect to DuckDB. Load `curated.dim_player` to a pandas DataFrame.
  - For each raw stats source (`raw.statsbomb_player_xg`, `raw.understat_player_xg`, `raw.squad_xg_ratings`):
    - Pull distinct player-row tuples to pandas.
    - Apply the three-tier matching from the High-Level Technical Design pseudo-logic:
      1. Tier 1: exact `(normalized_name, country_code, birth_year)` — requires DOB on the stats side; rarely true for raw stats, but tightest match.
      2. Tier 2: exact `(normalized_name, country_code)` — strong, works when source lacks DOB.
      3. Tier 3: `rapidfuzz.token_set_ratio ≥ 90` + at least one of (country match, club match). One candidate → match. Multiple → quarantine ambiguous.
    - Annotate each row with `player_id` (or `NULL`) and `match_tier` (`tier1` / `tier2` / `tier3` / `none`) and `match_reason` (`exact_with_dob` / `exact_no_dob` / `fuzzy_with_context` / `no_match` / `ambiguous_N`).
    - Write matched rows to `staging.matched_<source>` via DuckDB. Write unmatched rows to `quarantine.unmatched_<source>` (same row contents plus the `match_reason` column).
  - Log summary per source: `[match] <source>: M matched (tier1=X, tier2=Y, tier3=Z), U unmatched (no_match=A, ambiguous=B)`.
- Also update the per-source name attributes on `dim_player`: when a Tier 1/2/3 match succeeds for an Understat row, the matched player's `understat_name` column on `dim_player` should be set to the source's actual name (for future builds' Tier 2 to catch instantly). This is a UPDATE pass at the end of the matching phase, then `dim_player` gets re-flushed (write-back to `players.csv`). Decided: yes, do this — it shrinks the matching surface over time.

**Patterns to follow:**
- `from rapidfuzz import fuzz, process` import pattern already used in `tools/build_squad_xg_ratings.py`.
- `tools/lib/player_normalize.py` from Unit 2 for name normalization.

**Test scenarios:**
- Happy path: after running, `staging.matched_statsbomb_players` has the bulk of `raw.statsbomb_player_xg` rows, with `player_id` populated.
- Happy path: `quarantine.unmatched_statsbomb_players` has the residue (likely small, but non-empty initially — historical players, name oddities).
- Happy path: `SELECT match_tier, COUNT(*) FROM staging.matched_statsbomb_players GROUP BY 1` shows mostly Tier 1/2 hits.
- Happy path: re-running the script after a previous successful run — `dim_player.statsbomb_name` populated → Tier 2 hit rate is even higher.
- Edge case: a player in `raw.statsbomb_player_xg` is genuinely not in any WC2026 squad (e.g., a historical Euro2024 player not called up) → ends up in quarantine with `reason=no_match`. Verified count is non-zero but bounded.
- Edge case: a stats row has `country_code = NULL` → skip Tier 1 and 2, fall through to Tier 3 fuzzy.
- Edge case: a fuzzy match returns multiple candidates above threshold → `reason=ambiguous_2` (or N), row goes to quarantine with all candidate `player_id`s listed.
- Edge case: `dim_player.statsbomb_name` already populated for a player from a previous run, and the new run's source name has a slightly different spelling → Tier 2 should hit on the previously-saved spelling. Confirm by inspecting that `staging.matched_statsbomb_players.match_tier` predominantly says `tier2` after the second run.
- Edge case: a player appears in both StatsBomb and Understat with slightly different names → after matching, both rows resolve to the same `player_id`. Confirm: `SELECT player_id, COUNT(*) FROM staging.matched_<all_sources> GROUP BY 1 HAVING COUNT(*) > 1` returns expected counts.

**Verification:**
- `SELECT COUNT(*) FROM staging.matched_<source>` + `SELECT COUNT(*) FROM quarantine.unmatched_<source>` equals the distinct player-row count in `raw.<source>` for each source — no rows lost.
- Match rates logged at end of script: target >90% for WC2026-squad players in `raw.squad_xg_ratings` (since those should match the roster 1:1), and >70% for `raw.statsbomb_player_xg` (lower because it has historical players outside WC2026 squads).
- `dim_player.statsbomb_name` / `dim_player.understat_name` columns are populated for the matched players (write-back to `players.csv` confirmed).

- [ ] **Unit 5: Build the curated facts**

**Goal:** Build `curated.fact_player_xg` and `curated.fact_team_rating` from the matched staging tables and the raw rating tables, with FKs to dims.

**Requirements:** R5 (facts exist), R7 (row counts), R1 (full build command).

**Dependencies:** Unit 3 (dims), Unit 4 (matched staging tables).

**Files:**
- Create: `db/sql/curated/fact_player_xg.sql` — UNION of `staging.matched_<source>` tables, projected to a common schema: `(player_id, tournament_id, source, season_or_period, xg_per_90, minutes, xg_total, ...)`.
- Create: `db/sql/curated/fact_team_rating.sql` — long-format from `raw.team_ratings_all_models` (and individual model parquets if needed): `(team_code, model_id, as_of_date, rating_value, rating_type)`. `dim_team` and `dim_model` are joined to validate FKs (LEFT JOIN with NULL detection).
- Update: `tools/build_duckdb.py` — execute fact SQL files after the matching phase. Log row counts.

**Approach:**
- Each fact `.sql` is a single `CREATE OR REPLACE TABLE curated.fact_<name> AS SELECT ...`.
- `fact_player_xg`: every staging table is projected to the same column set (`player_id`, `tournament_id`, `source`, `xg_per_90`, `minutes`, `xg_total`, `npxg_per_90` (if available), `goals`, `assists`, `as_of_date`) and UNION ALL'd. Source-specific columns missing in one source are NULL.
  - `tournament_id` for StatsBomb rows is derived from the StatsBomb competition column (mapping in `dim_tournament`). For Understat rows, it's `null` (club xG isn't a tournament) or a synthetic `club_season_2526` ID if Unit 1 chose to include club rows. Final shape decided in Unit 1.
  - For Understat: most natural is a separate fact `fact_player_club_xg`, but to keep v1 lean, fold both into `fact_player_xg` with `tournament_id IS NULL` denoting "club xG". Reconsidered in v2.
- `fact_team_rating`: pivot `raw.team_ratings_all_models` (wide → long) so each (team_code, model) is one row. Join to `dim_team` and `dim_model` to verify FKs. Rows with no matching dim are dropped and logged.
- Build script logs:
  - `[fact] fact_player_xg: <count> rows (<count_with_tournament> tournament, <count_without> club)`
  - `[fact] fact_team_rating: <count> rows; <count_orphan> dropped (orphan FKs)`

**Patterns to follow:**
- DuckDB's `UNION ALL` for the multi-source consolidation.
- LEFT JOIN + IS NULL pattern for orphan-FK detection.

**Test scenarios:**
- Happy path: `SELECT * FROM curated.fact_player_xg LIMIT 10` returns rows with valid `player_id`s.
- Happy path: `SELECT * FROM curated.fact_player_xg JOIN curated.dim_player USING (player_id) WHERE display_name LIKE 'Lionel Messi'` returns Messi's xG rows from all sources.
- Happy path: `SELECT model_id, COUNT(DISTINCT team_code) FROM curated.fact_team_rating GROUP BY 1` shows expected model coverage.
- Happy path: idempotency — re-running build produces identical fact row counts.
- Edge case: an orphan team_code in `raw.team_ratings_all_models` (drift from a recent run) → dropped from `fact_team_rating`, count logged. Build doesn't fail.
- Edge case: a staging table is empty (all rows quarantined) → `fact_player_xg` is built from the remaining sources; logged but doesn't fail.
- Integration: a query joining `fact_player_xg` + `dim_player` + `dim_tournament` returns sensible scorer lists per tournament — top WC2022 xG scorers should be familiar names (Messi, Mbappé, Giroud).

**Verification:**
- `SHOW TABLES FROM curated` lists all four dims + both facts.
- Sample analytic query returns plausible results (top 10 players by total xG, top 10 teams by mean rating).
- All FK joins succeed (no NULL `player_id`/`team_code` in fact tables).

- [ ] **Unit 6: Verify, document, and "test DuckDB"**

**Goal:** A verify script for automated sanity, a README that makes the DB self-documenting, and a set of example analytical queries the user can run to test DuckDB hands-on the moment the build finishes.

**Requirements:** R8, R9, R10.

**Dependencies:** Units 2–5 (everything must exist for verification and docs to point at real things).

**Files:**
- Create: `tools/verify_duckdb.py` — sanity assertions with `[PASS]`/`[FAIL]` output and non-zero exit on failure.
- Create: `db/README.md` — build, query, refresh workflows.
- Create: `db/queries/examples/top_scorers_blended_xg.sql` — top-20 players by combined fact_player_xg.
- Create: `db/queries/examples/model_agreement_matrix.sql` — pivot fact_team_rating to (team, model) matrix; the "Golden Zone" view is a one-step extension.
- Create: `db/queries/examples/attack_vs_defense_per_team.sql` — joined view of attack and defense ratings, scatter-plot-ready.
- Create: `db/queries/examples/squad_coverage_gaps.sql` — players in dim_player (WC2026 squads) with no row in fact_player_xg, i.e., players we have no xG data for.
- Create: `db/queries/examples/inspect_quarantine.sql` — `SELECT * FROM quarantine.unmatched_<source>` for review.
- Update: `DEVELOPMENT.md` — one-paragraph "Database" subsection under Architecture, pointing at `db/README.md`.

**Approach:**
- `tools/verify_duckdb.py`:
  - `argparse`: `--db-path`.
  - List of named assertions, each `(name, sql, predicate)`. Categories: row count ranges, no-NULL on PK columns, FK integrity (every `fact_player_xg.player_id` in `dim_player`), registry hygiene (no duplicate `(normalized_name, country_code, birth_year)` in `dim_player`), source coverage (every expected raw table non-empty), quarantine surface (warn if quarantine non-empty; not fail).
  - Print `[PASS]`/`[FAIL]` per assertion with actual value. Exit code = number of failures.
- `db/README.md` structure:
  - "What this is" — one paragraph.
  - "Build it" — `python3 tools/build_duckdb.py`. One line each on raw → dims → matching → facts.
  - "Test it" — `duckdb data/wc2026.duckdb`. Five copy-paste-able queries from `db/queries/examples/`.
  - "Verify it" — `python3 tools/verify_duckdb.py`.
  - "Refresh a master" — when WC2026 final rosters drop (~Jun 4): run the roster scraper, then `python3 tools/refresh_player_master.py`, then `python3 tools/build_duckdb.py`. Player IDs persist.
  - "Triage quarantine" — `SELECT * FROM quarantine.unmatched_<source>`; manual review; either add a row to `players.csv` for a genuinely new player, or correct a name in `players.csv` to make the next build's matcher hit.
  - "Schema overview" — short table of curated tables with one-line descriptions; link to `db/SCHEMA.md` for full column docs.
  - "Adding a new table" — checklist.
- Each example query in `db/queries/examples/*.sql` is a single statement with a leading comment block explaining the analytical question, expected output shape, and how to interpret.

**Patterns to follow:**
- DuckDB CLI is the testing surface: `duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/top_scorers_blended_xg.sql)"`.
- README tone matches root `README.md` and `DEVELOPMENT.md` — terse, list-driven, no marketing.

**Test scenarios:**
- Happy path: `python3 tools/verify_duckdb.py` on a freshly-built DB exits 0 with all `[PASS]`.
- Happy path: every example query in `db/queries/examples/` runs against the built DB and returns sensible rows (not empty, not error). The user can run all five back-to-back.
- Happy path: the README's "Refresh a master" section is followable cold — a future contributor can run those three commands and see the master update without asking for help.
- Edge case: verify script with a deliberately-corrupted DB (e.g., manually `DROP TABLE curated.dim_player`) exits non-zero with a clear error.
- Edge case: an example query whose underlying data is empty (e.g., quarantine query when all rows matched) returns "no rows" cleanly, not an error.

**Verification (this is "test DuckDB"):**
- `python3 tools/build_duckdb.py && python3 tools/verify_duckdb.py && duckdb data/wc2026.duckdb` → user is dropped into a working DuckDB shell against the built DB.
- User runs `.read db/queries/examples/top_scorers_blended_xg.sql` (or copy-pastes the contents) and sees a list of familiar top scorers.
- User runs the model-agreement matrix query and sees per-team ratings from each model side by side.
- User runs the quarantine query and inspects which stats rows didn't match — this is the data-quality feedback loop in action.
- After this unit, the user has both an automated proof of correctness (`verify_duckdb.py`) and a hands-on exploration surface (DuckDB CLI + example queries).

## System-Wide Impact

- **Interaction graph:** All five new tools (`build_duckdb.py`, `refresh_player_master.py`, `match_sources_to_masters.py`, `verify_duckdb.py`, `inspect_parquets.py`) are leaf scripts. They consume `data/derived/*.parquet` and `db/masters/*.csv` and produce `data/wc2026.duckdb`. No existing pipeline script is modified.
- **Error propagation:** Missing parquet → clear error at raw phase. Missing master → clear error at dim phase. Stats source with all rows quarantined → fact table built from remaining sources, count logged. Verify script catches every other class of failure post-build.
- **State lifecycle risks:** The DB is fully derived from `db/masters/` + `data/derived/`. The only persistent state is the masters (committed CSVs). A clean clone + parquet pull + `python3 tools/build_duckdb.py` reproduces the entire DB.
- **API surface parity:** The curated layer is the contract for any future viz/analysis consumer. `db/SCHEMA.md` is the canonical reference. Breaking changes to curated columns require updating SCHEMA.md and the verify script.
- **Integration coverage:** Build + verify exercise raw load, master read, dim build, matching tiers, quarantine, fact build, FK integrity, and example-query execution. End-to-end coverage of the pipeline.
- **Unchanged invariants:** No pipeline script modified. No parquet schema modified. `ensemble_model.py` and `wc2022_xg_backtest.py` continue to consume parquets directly; this plan does not migrate them.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| WC2026 final rosters aren't out until ~Jun 4; v1 uses preliminary squad data, so `players.csv` may have churn before final rosters land. | Master-refresh tool (Unit 2) handles this exact case — when finals drop, refresh re-runs match the new roster against existing IDs and preserve them for unchanged players. Plan for one larger refresh in early June; subsequent refreshes will be tiny. |
| First-build bootstrap is permissive — duplicates in the source roster could produce duplicate `player_id`s. | First commit of `players.csv` requires a human review pass (called out in Unit 2). Verify script also checks for duplicate `(normalized_name, country_code, birth_year)` post-build. |
| Quarantine accumulates if no one triages it — silent loss of fact rows. | Verify script (Unit 6) warns on non-empty quarantine. README documents the triage workflow. Quarantine count is a long-term health metric. |
| Birth year missing from some sources or roster pages → Tier 2 fallback only, weaker matching. | Acceptable degradation; documented in SCHEMA.md. Roster scrape can be improved post-v1 to add DOB where missing. |
| `data/derived/*.parquet` and `data/wc2026.duckdb` are gitignored — fresh clone can't build without pulling derived data. | Same constraint as existing project. Documented in README. Masters survive clones, so `player_id`s persist. |
| DuckDB WAL files left behind on interrupted builds. | Gitignored. README documents the recovery (delete `.duckdb` + `.duckdb-wal`, re-run). |
| Match thresholds (rapidfuzz ≥90) are tuned to current data; new sources may need re-tuning. | Single source of truth in `tools/match_sources_to_masters.py`; verify script flags low match rates as a warning. |
| Historical players (in WC2022 StatsBomb data but not in WC2026 squads) get heavily quarantined. | Expected behavior — they're not in our master. Future plan can introduce historical-tournament masters if needed; for v1, they're correctly out of scope. |
| Player legitimately changes country (dual-nationality switch) — looks like a new player to the matcher. | Out of v1 scope. Caught by quarantine review. |

## Documentation / Operational Notes

- `db/README.md` (Unit 6) is the primary doc artifact for daily use.
- `db/SCHEMA.md` (Unit 1) is the data-model contract — first thing updated when any curated table changes.
- `DEVELOPMENT.md` gets a one-paragraph "Database" subsection pointing at `db/README.md` and the build command.
- No env vars, no secrets, no deployment. The DB is a local derived artifact.
- Masters are committed to git. Every change to a master is a reviewable PR diff.

## Sources & References

- **Origin document:** none (direct planning entry, evolved across three iterations on 2026-05-13).
- Related code: `tools/build_squad_xg_ratings.py` (script-style pattern), `tools/weekly_pull.py` (FIFA code dicts), `tools/pull_wc2026_squads.py` (roster source), `ensemble_model.py` (current pandas consumers).
- Related docs: `DEVELOPMENT.md` (canonical parquet set, FIFA-code policy), prior plans in `docs/plans/`.
- Memory: `feedback_player_identity_registry.md` (MDM principle for this project), `project_data_sources.md` (parquet inventory), `wc2026_live_pipeline_plan.md` (Jun 4 refresh trigger).
- DuckDB documentation: <https://duckdb.org/docs/api/python/overview>, <https://duckdb.org/docs/data/parquet/overview>, <https://duckdb.org/docs/data/csv/overview>.
