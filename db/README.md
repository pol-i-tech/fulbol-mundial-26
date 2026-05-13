# db/ — DuckDB Analytics Database

`data/wc2026.duckdb` is the project's analytics surface: a single DuckDB
file that joins everything in `data/derived/` into a clean dim/fact
schema, with stable player surrogate keys and source-to-master matching
already resolved. Built end-to-end by one command, queryable from the
`duckdb` CLI or any Python/Node/Rust DuckDB client.

For the full data-model contract see [`SCHEMA.md`](./SCHEMA.md).

## TL;DR

```bash
# Build it
python3 tools/build_duckdb.py

# Verify it
python3 tools/verify_duckdb.py

# Test it
duckdb data/wc2026.duckdb
```

Inside the DuckDB shell, copy-paste any of the queries in
[`queries/examples/`](./queries/examples/) to start exploring.

## Architecture (1-minute version)

```
db/masters/*.csv         (committed source of truth — surrogate keys live here)
data/derived/*.parquet   (existing parquet pipeline outputs)
        │
        ▼  python3 tools/build_duckdb.py
data/wc2026.duckdb
   ├── raw.*           (20 tables, 1:1 with parquets)
   ├── curated.*       (4 dims, 2 facts)
   ├── staging.*       (matched-stats intermediates + team-name resolver)
   └── quarantine.*    (unmatched rows; review queue)
```

Three principles:

1. **Master data drives dims.** `dim_player` is sourced from
   `db/masters/players.csv` (the player master). Raw stats sources are
   matched *to* `dim_player`; nothing extends the master from facts.
2. **Player identity is a stable internal surrogate key**, format
   `P######`, assigned once and never reused.
3. **Unmatched stats rows go to quarantine, not silent drop.** Every
   data-quality issue is visible.

## Build pipeline

Single command, four phases:

```bash
python3 tools/build_duckdb.py
```

| Phase | What it does | Result |
|---|---|---|
| **raw** | `CREATE OR REPLACE TABLE raw.<name>` for every parquet in `data/derived/` | 20 tables, ~38,000 rows |
| **dim** | Load `db/masters/*.csv` into `curated.dim_*` via the SQL files in `db/sql/curated/` | 4 dim tables, ~1,400 rows |
| **match** | Resolve `player_id` for every raw stats row → `staging.matched_*` + `quarantine.unmatched_*`; write source-name caches back to `players.csv` | 4 staging, 4 quarantine tables |
| **fact** | UNION matched stats into `curated.fact_player_xg`; unpivot rating tables into `curated.fact_team_rating` | 2 fact tables, ~2,700 rows |

Everything is `CREATE OR REPLACE TABLE`; running the script twice
produces the same DB. Build time on a clean run is ~10 seconds.

### Build flags

```bash
python3 tools/build_duckdb.py --skip-raw    # rebuild dims only (faster during dev)
python3 tools/build_duckdb.py --skip-match  # skip the matching layer
python3 tools/build_duckdb.py --db-path /tmp/test.duckdb  # alternate location
```

## Test it (the "test DuckDB" workflow)

```bash
duckdb data/wc2026.duckdb
```

Then copy-paste any of these example queries:

| Example | What it shows |
|---|---|
| [`queries/examples/top_scorers_blended_xg.sql`](./queries/examples/top_scorers_blended_xg.sql) | Top 20 by combined StatsBomb + Understat xG. The cross-source join via `player_id` is the whole point of the MDM design. |
| [`queries/examples/model_agreement_matrix.sql`](./queries/examples/model_agreement_matrix.sql) | Per-team rating matrix across the M1_History / M2_Season / M3_RecentForm layers. The "Golden Zone" rule (all three agree) is a one-step filter. |
| [`queries/examples/attack_vs_defense_per_team.sql`](./queries/examples/attack_vs_defense_per_team.sql) | Attack rating vs defense rating per WC2026 qualifier. Scatter-plot-ready. |
| [`queries/examples/squad_coverage_gaps.sql`](./queries/examples/squad_coverage_gaps.sql) | Players in the master with no fact rows — a drift sentinel. Should return empty on a healthy build. |
| [`queries/examples/inspect_quarantine.sql`](./queries/examples/inspect_quarantine.sql) | Per-source quarantine counts. Where data-quality issues live. |

Or run any of them from the shell:

```bash
duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/top_scorers_blended_xg.sql)"
```

## Verify it

```bash
python3 tools/verify_duckdb.py
```

Runs 27 sanity assertions covering: schema presence, row count ranges,
PK non-NULL + uniqueness, `P######` ID format, registry hygiene (no
duplicate normalized names within a country), FK integrity across facts,
source coverage, match rate floors, and quarantine surface. Exit code
is the number of FAIL'd assertions; WARNs do not fail.

Run after every build, or as a CI gate.

## Refresh a master (when source data changes)

Three independent refresh tools — each safe to re-run; output is sorted
for stable git diffs.

### Player master

```bash
python3 tools/refresh_player_master.py
```

Reads `data/raw/squads/wc2026_squads_confirmed.json` if it contains
player records (post ~Jun 4, 2026 when FIFA finalizes squads); falls
back to `data/derived/squad_xg_ratings.parquet` otherwise. Preserves
existing `player_id` values for players still in the roster; assigns
new `P######` IDs only for genuine new players; marks players who drop
out as `is_active = false` but never deletes rows.

### Team master

```bash
python3 tools/refresh_team_master.py
```

Generated from `tools/weekly_pull.py:NAME_TO_FIFA3` + a non-WC2026
supplement + a hand-coded confederation map. Re-run when a new team
appears in any data source.

### Model master

```bash
python3 tools/refresh_model_master.py
```

Scans `results/*/MODEL.md` files. Re-run when a model dir adds a
MODEL.md or when an existing one updates its validation status.

### Tournament master

`db/masters/tournaments.csv` is hand-curated. Edit directly when a new
tournament needs registering. Aligned to the `season` column values in
the StatsBomb parquets.

## Triage quarantine

After a build, if `quarantine.unmatched_*` tables are non-empty:

```sql
duckdb data/wc2026.duckdb
SELECT player, team, match_reason
FROM quarantine.unmatched_sb_player_stats_pedigree
LIMIT 20;
```

Two valid resolutions:

1. **Genuinely new player** — manually add a row to `db/masters/players.csv`
   with a new `P######` ID following the next sequential number. Commit.
2. **Missed match** — the player IS in the master but the source name
   diverges enough that fuzzy matching missed it. Find the existing
   `player_id` in `players.csv`, set its `statsbomb_name` (or
   `understat_name` / `understat_id`) column to the source's spelling.
   Commit. Next build's Tier 2 matching catches it instantly.

After either change, re-run `python3 tools/build_duckdb.py`.

## Schema overview

| Table | Purpose | Source |
|---|---|---|
| `curated.dim_player` | Player master (wide; SCD Type 1) | `db/masters/players.csv` |
| `curated.dim_team` | FIFA team list + confederation + WC2026 qualifier flag | `db/masters/teams.csv` |
| `curated.dim_tournament` | Tournament enumeration | `db/masters/tournaments.csv` |
| `curated.dim_model` | Models with MODEL.md cards | `db/masters/models.csv` |
| `curated.fact_player_xg` | Player xG by source × period | matched StatsBomb + Understat |
| `curated.fact_team_rating` | Team rating by layer (attack / defense / M1 / M2 / M3) | raw rating tables |
| `staging.matched_<source>` | Raw stats with `player_id` resolved | matching layer |
| `quarantine.unmatched_<source>` | Stats rows that failed to match the master | matching layer |

See [`SCHEMA.md`](./SCHEMA.md) for the column-level contract.

## Adding a new table

1. Update [`SCHEMA.md`](./SCHEMA.md) — define the table, columns, source.
2. If it's a dim: create `db/sql/curated/dim_<name>.sql` and add it to
   `DIM_SQL_FILES` in `tools/build_duckdb.py`. Add a master CSV at
   `db/masters/<name>.csv`.
3. If it's a fact: create `db/sql/curated/fact_<name>.sql` and add it
   to `FACT_SQL_FILES`. Reference dim tables via the proper FK columns.
4. If it's a new raw source: add the parquet → table mapping to
   `RAW_TABLES` in `tools/build_duckdb.py`.
5. Add a verification assertion to `tools/verify_duckdb.py`.
6. Run `python3 tools/build_duckdb.py && python3 tools/verify_duckdb.py`.
7. Add an example query to `db/queries/examples/` if it unlocks a new
   analytical lens.

## Known gaps

See [the plan's "Deferred to Separate Tasks" section](../docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md#deferred-to-separate-tasks).

- Visualization tool on top of this DB — separate plan.
- Market snapshots → `fact_market_price`. Schema TBD.
- Model predictions → `fact_prediction`. Wide and varies; deserves its own pass.
- `fact_match` from FIFA fixture list — needs a separate ingestion script.
- Live in-tournament refresh from Sofascore / API-Football (~Jun 4 trigger).
