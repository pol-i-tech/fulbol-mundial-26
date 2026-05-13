# db/SCHEMA.md — DuckDB Analytics Database Schema

**Status:** active design (v1); committed before any DDL is written.
**Plan:** [docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md](../docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md)

This document is the contract for the DuckDB database at `data/wc2026.duckdb`. It specifies the four authoritative masters, the raw load layer, the curated dim/fact layer, the source-to-master matching algorithm, and the quarantine schema for unmatched rows.

**Design principle: master-data-management (MDM).** Every dim has an authoritative master source. Facts reference dims via stable surrogate keys (`player_id`) or canonical natural keys (`team_code`). Source stats are matched *to* the masters one-way; nothing extends a master from a fact source.

---

## Schemas (DuckDB namespaces)

| Schema | Purpose | Lifecycle |
|---|---|---|
| `raw` | 1:1 mirrors of `data/derived/*.parquet`. No transformations. | `CREATE OR REPLACE TABLE` on every build. |
| `curated` | Authoritative dims (`dim_*`) and analytical facts (`fact_*`). | `CREATE OR REPLACE TABLE` on every build. |
| `staging` | Intermediate per-source tables produced by the matching layer (raw stats with `player_id` resolved). | `CREATE OR REPLACE TABLE` on every build. |
| `quarantine` | Raw stats rows that failed to match a master, with `reason` column. | `CREATE OR REPLACE TABLE` on every build. |

---

## Masters (committed CSVs at `db/masters/`)

The four masters are the only persistent state in this database. They survive DB rebuilds, survive clean clones, and carry surrogate keys that never change.

### `db/masters/players.csv` — the player master

**Primary key:** `player_id` (string, format `P######`, sequential, zero-padded to 6 digits).

**Source provenance (v1):** built from `data/derived/squad_xg_ratings.parquet` (1,275 rows = WC2026 candidate pool with nation/player/position/club/league). The roster JSON at `data/raw/squads/wc2026_squads_confirmed.json` is **currently a placeholder** (only contains a list of pending country names with no player data); when actual squad data lands (expected ~Jun 4 when FIFA finalizes rosters), the refresh tool's roster-JSON path activates and adds DOB, jersey number, and any other roster fields. Unit 2's `tools/refresh_player_master.py` is built to handle both sources.

**Columns:**

| Column | Type | Source | Description |
|---|---|---|---|
| `player_id` | VARCHAR | assigned at master ingest | Stable surrogate key, never reassigned. Format `P######`. |
| `display_name` | VARCHAR | `squad_xg_ratings.player` (or roster JSON `name` when available) | Canonical display form. Wins source priority: roster JSON > squad_xg_ratings. |
| `normalized_name` | VARCHAR | derived | `unicodedata.NFKD` → ASCII → lowercase → collapse whitespace → strip non-alphanumeric. Used by the matching layer. |
| `country_code` | VARCHAR(3) | `squad_xg_ratings.nation` → mapped via `tools/weekly_pull.py:NAME_TO_FIFA3` | FIFA 3-letter code. Canonical for cross-table joins. |
| `nation_name` | VARCHAR | `squad_xg_ratings.nation` | Display form preserved (e.g., "South Africa"). |
| `birth_date` | DATE | roster JSON (NULL in v1 until rosters drop) | Used by Tier 1 matching. |
| `birth_year` | INTEGER | derived from `birth_date`; NULL when DOB missing | Used by Tier 1 matching. |
| `position` | VARCHAR | `squad_xg_ratings.position` | Free-form, e.g., `"F"`, `"M S"`, `"D"`. Single-letter or compact mapping. |
| `current_club` | VARCHAR | `squad_xg_ratings.club` | May be NULL if unknown at squad time. |
| `current_league` | VARCHAR | `squad_xg_ratings.league` | May be NULL. |
| `statsbomb_name` | VARCHAR | populated by matching layer when an SB row resolves to this `player_id` | Cached for next-build Tier-2 fast path. |
| `understat_id` | VARCHAR | populated by matching layer from Understat `player_id` column | Persisted because Understat carries a stable internal ID. Gold standard for re-matching. |
| `understat_name` | VARCHAR | populated by matching layer | Cached form. |
| `is_active` | BOOLEAN | TRUE if present in latest master refresh; FALSE if dropped | Never deleted. |
| `first_seen_at` | DATE | set at first ingest | Audit. |
| `last_updated_at` | DATE | set on every refresh that touches the row | Audit. |

**Cardinality expectations (v1):**
- Initial commit: ~1,275 rows (one per `squad_xg_ratings.parquet` player).
- Post-roster-drop refresh (~Jun 4): may grow to ~1,248 confirmed (48 teams × 26-player roster cap) plus inactive rows for players who don't make final squads (we keep them with `is_active = false`).

**Identity discipline:**
- A `player_id` is assigned **once**, never reused, never reassigned.
- The matching key for ID preservation across refreshes is `(normalized_name, country_code, birth_year)` when DOB is available, falling back to `(normalized_name, country_code)`.
- Hand-edits to `players.csv` are accepted — the refresh tool doesn't try to "undo" them.

### `db/masters/teams.csv` — the team master

**Primary key:** `team_code` (string, FIFA 3-letter code; natural key, no surrogate).

**Source provenance:** derived from `tools/weekly_pull.py:NAME_TO_FIFA3` and `:ISO2_TO_FIFA3` dicts (one-shot generation script in Unit 2). Confederation column is hand-added (FIFA's 6 confederations are stable).

**Columns:**

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FIFA 3-letter code, e.g., `MEX`, `ARG`, `BRA`. |
| `team_name` | VARCHAR | Canonical display name, e.g., `"Mexico"`. Sourced from `NAME_TO_FIFA3` keys (deduped). |
| `iso2_code` | VARCHAR(2) | When known, the ISO 3166-1 alpha-2 code; NULL otherwise (some FIFA codes don't have a clean ISO mapping). |
| `confederation` | VARCHAR | One of `AFC`, `CAF`, `CONCACAF`, `CONMEBOL`, `OFC`, `UEFA`. Hand-mapped. |
| `is_wc2026_qualifier` | BOOLEAN | TRUE for the 48 confirmed/pending WC2026 teams. |

**Cardinality:** ~70–80 rows (the union of countries appearing in `NAME_TO_FIFA3` keys). FIFA has 211 member associations but our `NAME_TO_FIFA3` dict only covers teams the project has touched — that's fine for v1.

### `db/masters/tournaments.csv` — the tournament master

**Primary key:** `tournament_id` (string slug).

**Source provenance:** hand-curated. Tiny enumeration table.

**Columns:**

| Column | Type | Description |
|---|---|---|
| `tournament_id` | VARCHAR | Slug. One of: `wc2026`, `wc2022`, `wc2018`, `euro2024`, `euro2020`, `copa2024`, `copa2021`. |
| `tournament_name` | VARCHAR | Display, e.g., `"FIFA World Cup 2022"`. |
| `start_date` | DATE | First match date. |
| `end_date` | DATE | Final date. |
| `host_country` | VARCHAR | Display name of host (or `"USA/MEX/CAN"` for joint hosts). |
| `competition_type` | VARCHAR | `"world_cup"`, `"euros"`, `"copa_america"`. |

**Cardinality:** 6–8 rows initially.

**Note:** The values in this master must match the `competition`/`season` values used in `raw.sb_player_stats` and `raw.statsbomb_player_xg` after mapping (StatsBomb's `"FIFA World Cup 2022"` ↔ `tournament_id = wc2022`). The mapping is baked into the matching layer.

### `db/masters/models.csv` — the model master

**Primary key:** `model_id` (string; directory name under `results/`).

**Source provenance:** auto-derived by scanning `results/*/MODEL.md` files at Unit 2 build time. The directory name becomes `model_id`; columns are parsed from the MODEL.md table.

**Columns:**

| Column | Type | Description |
|---|---|---|
| `model_id` | VARCHAR | Slug = directory name. E.g., `elo-baseline`, `ensemble-v2`, `poisson-xg`. |
| `model_name` | VARCHAR | Display name from MODEL.md. |
| `model_type` | VARCHAR | `"baseline"`, `"compound"`, `"single-source"`. Hand-classified or parsed from MODEL.md. |
| `methodology_path` | VARCHAR | Repo-relative path to `methodology/<dir>/` or the canonical implementation file. |
| `results_path` | VARCHAR | Repo-relative `results/<dir>/`. |
| `last_validation_status` | VARCHAR | Parsed from MODEL.md "Validation status" row. |

**Cardinality:** 9–10 rows (one per directory under `results/` excluding `_template` and `comparisons`).

---

## Raw layer — `raw.*`

Every in-scope parquet from `data/derived/` becomes a `raw.<table>` table via `CREATE OR REPLACE TABLE raw.<table> AS SELECT * FROM read_parquet('data/derived/<file>.parquet')`. **Schemas are 1:1 with the parquets — no transformations.** The inspect script's output is the authoritative column inventory (run `python3 tools/inspect_parquets.py`).

**In-scope parquets (20 files, mapped to `raw.<name>`):**

| Parquet | `raw.<name>` | Rows | Grain | Role |
|---|---|---|---|---|
| `squad_xg_ratings.parquet` | `raw.squad_xg_ratings` | 1,275 | one row per (nation, player) | **Primary player-master source.** Wide table with national+club xG joined. |
| `team_attack_ratings.parquet` | `raw.team_attack_ratings` | 52 | one row per nation | Attack rating per team. |
| `team_defensive_ratings.parquet` | `raw.team_defensive_ratings` | 48 | one row per nation | Defense rating per team. |
| `team_ratings_all_models.parquet` | `raw.team_ratings_all_models` | 48 | one row per nation; wide on model | Cols `M1_History`, `M2_Season`, `M3_RecentForm` — unpivoted into `fact_team_rating`. |
| `team_attack_ratings_wc2022.parquet` | `raw.team_attack_ratings_wc2022` | 32 | per nation | Historical (WC2022 cut). |
| `team_defense_ratings_wc2022.parquet` | `raw.team_defense_ratings_wc2022` | 32 | per nation | Historical (WC2022 cut). |
| `team_xga_pedigree.parquet` | `raw.team_xga_pedigree` | 56 | (nation, competition) | Tournament defense pedigree. |
| `defensive_ratings_tournament.parquet` | `raw.defensive_ratings_tournament` | 52 | per team | National-tournament defensive metrics. |
| `defensive_ratings_club_2526.parquet` | `raw.defensive_ratings_club_2526` | 96 | per club | Club-level current-season defense. |
| `statsbomb_player_xg.parquet` | `raw.statsbomb_player_xg` | 6,619 | per shot (event-grain) | NOT a direct fact source; aggregated downstream. |
| `statsbomb_team_xg.parquet` | `raw.statsbomb_team_xg` | 524 | per (match, team) | Match-level team xG. |
| `sb_player_stats.parquet` | `raw.sb_player_stats` | 4,599 | per (player, match) | Per-match player stats. |
| `sb_player_summary.parquet` | `raw.sb_player_summary` | 1,275 | per player (aggregated across tournaments) | Direct source for `fact_player_xg` StatsBomb rows. |
| `sb_player_summary_pre_wc22.parquet` | `raw.sb_player_summary_pre_wc22` | 657 | per player (pre-WC22 aggregation) | Used for WC22 backtest baselining. |
| `sb_player_stats_pedigree.parquet` | `raw.sb_player_stats_pedigree` | 740 | per (player, tournament) | Per-tournament pedigree for `fact_player_xg`. |
| `squad_wc2022_proxy.parquet` | `raw.squad_wc2022_proxy` | 680 | per (player, team) | WC2022 squad proxy. |
| `understat_player_xg.parquet` | `raw.understat_player_xg` | 6,808 | per player (aggregated club career) | Direct source for `fact_player_xg` Understat rows. |
| `understat_player_xg_raw.parquet` | `raw.understat_player_xg_raw` | 9,766 | per (player, league, season) | Detailed per-season Understat. |
| `understat_2122_players.parquet` | `raw.understat_2122_players` | 2,242 | per player (2021-22 season) | Historical season. |
| `understat_2526_players.parquet` | `raw.understat_2526_players` | 2,758 | per player (current 2025-26 season) | Current season; matches WC2026 squad timing. |

---

## Curated dims — `curated.dim_*`

Each curated dim is built by `CREATE OR REPLACE TABLE curated.dim_<name> AS SELECT [columns with types] FROM read_csv('db/masters/<name>.csv', ...)`. The DuckDB tables mirror the CSV columns exactly with explicit types declared in the SQL.

### `curated.dim_player`

- **Primary key:** `player_id`
- **Source:** `db/masters/players.csv`
- **Cardinality:** ~1,275 (will grow modestly after roster refreshes)
- **Columns:** all columns from `players.csv` (see master section above)
- **Used by:** every `fact_*` table that references players; the matching layer writes back `statsbomb_name`, `understat_name`, `understat_id` columns here

### `curated.dim_team`

- **Primary key:** `team_code` (FIFA 3-letter, natural key)
- **Source:** `db/masters/teams.csv`
- **Cardinality:** ~70–80
- **Columns:** `team_code`, `team_name`, `iso2_code`, `confederation`, `is_wc2026_qualifier`

### `curated.dim_tournament`

- **Primary key:** `tournament_id`
- **Source:** `db/masters/tournaments.csv`
- **Cardinality:** 6–8
- **Columns:** `tournament_id`, `tournament_name`, `start_date`, `end_date`, `host_country`, `competition_type`

### `curated.dim_model`

- **Primary key:** `model_id`
- **Source:** `db/masters/models.csv`
- **Cardinality:** ~9–10
- **Columns:** `model_id`, `model_name`, `model_type`, `methodology_path`, `results_path`, `last_validation_status`

---

## Matching contract — source stats → `player_id`

Goal: every raw stats row that references a player gets a `player_id` resolved from `curated.dim_player`. Implemented in `tools/match_sources_to_masters.py` (Unit 4).

### Inputs per raw row

For each row in `raw.statsbomb_player_xg`, `raw.sb_player_summary`, `raw.sb_player_stats_pedigree`, `raw.understat_player_xg`, `raw.understat_2526_players`:

- `source_name` — the source's player-name column (`player`).
- `source_country` — country if the source carries it: `team` for StatsBomb (national team only in tournament data), `nationality` for Understat. NULL for club-grain Understat without nationality.
- `source_birth_year` — currently never populated; reserved for when roster master adds DOB.
- `source_player_id` — for Understat sources, the source's stable `player_id` (gold standard for re-matching). NULL for StatsBomb.

### Algorithm (three tiers, ordered)

```
def resolve(row, dim_player):
    norm = normalize(row.source_name)

    # TIER 0: Understat ID match (when source carries understat_id and dim has it)
    if row.source == "understat" and row.source_player_id:
        hit = dim_player.where(understat_id == row.source_player_id)
        if len(hit) == 1: return hit.player_id, "tier0_understat_id"

    # TIER 1: exact (normalized_name, country_code, birth_year) — strongest
    if row.source_country and row.source_birth_year:
        cc = normalize_country(row.source_country)  # FIFA3
        hits = dim_player.where(normalized_name == norm
                              & country_code == cc
                              & birth_year == row.source_birth_year)
        if len(hits) == 1: return hits.player_id, "tier1_exact_with_dob"
        if len(hits) > 1: return None, f"ambiguous_tier1_{len(hits)}"

    # TIER 2: exact (normalized_name, country_code) — strong without DOB
    if row.source_country:
        cc = normalize_country(row.source_country)
        hits = dim_player.where(normalized_name == norm & country_code == cc)
        if len(hits) == 1: return hits.player_id, "tier2_exact_no_dob"
        if len(hits) > 1: return None, f"ambiguous_tier2_{len(hits)}"

    # TIER 3: fuzzy ≥ 90 token_set_ratio + at least one shared context field
    candidates = rapidfuzz.process.extract(
        norm, dim_player.normalized_name,
        scorer=fuzz.token_set_ratio, score_cutoff=90)
    candidates_with_context = [c for c in candidates
                                if c.country_code == cc
                                or c.current_club == row.source_club]
    if len(candidates_with_context) == 1: return c.player_id, "tier3_fuzzy"
    if len(candidates_with_context) > 1: return None, f"ambiguous_tier3_{len(candidates_with_context)}"

    return None, "no_match"
```

### v1 reality check (DOB unavailable)

Tier 1 is **dormant in v1** — no source carries birth_year yet, and the master doesn't have DOB until rosters drop. The primary deterministic key is Tier 2: `(normalized_name, country_code)`.

For Understat → master matching, Tier 0 (Understat ID) is the strongest signal because Understat carries a stable internal `player_id` we persist on `dim_player.understat_id`. After the first match, every subsequent build hits Tier 0 for previously-matched Understat players.

### Outputs per source

For each source S:

- `staging.matched_<S>` — every row from `raw.<S>` augmented with `player_id` and `match_tier`. Source's original columns preserved.
- `quarantine.unmatched_<S>` — every unmatched row, augmented with `match_reason` (`no_match`, `ambiguous_tier1_2`, `ambiguous_tier3_3`, etc.) and the candidate `player_id` list (CSV string).

### Write-back to `dim_player`

After matching completes, the script also UPDATEs `curated.dim_player` (and writes back to `db/masters/players.csv`):

- For every Tier 0/1/2/3 match, set `statsbomb_name` / `understat_name` / `understat_id` on the matched row.
- This shrinks the matching surface over time — next build's identical source name hits Tier 2 instantly via the cached source-specific name column.

---

## Curated facts — `curated.fact_*`

### `curated.fact_player_xg`

- **Grain:** one row per `(player_id, source, period_id)`. `period_id` is a `tournament_id` for StatsBomb-tournament data, or a season identifier (e.g., `club_2526`) for Understat club data.
- **Primary key:** `(player_id, source, period_id)`
- **Source SQL:** UNION ALL across:
  - `staging.matched_sb_player_stats_pedigree` projected with `source = 'statsbomb'`, `period_id = tournament_id_lookup(competition)`.
  - `staging.matched_understat_player_xg` projected with `source = 'understat'`, `period_id = 'club_career_aggregated'`.
  - `staging.matched_understat_2526_players` projected with `source = 'understat'`, `period_id = 'club_2526'`.
- **FK constraints (LEFT JOIN + IS NULL check at build time, not enforced by DuckDB):**
  - `player_id` exists in `curated.dim_player`
  - `period_id` exists in `curated.dim_tournament` (when not a club-season)
- **Columns:**

| Column | Type | Description |
|---|---|---|
| `player_id` | VARCHAR | FK to `dim_player`. |
| `source` | VARCHAR | One of `'statsbomb'`, `'understat'`. |
| `period_id` | VARCHAR | `tournament_id` for tournament data, season slug for club data (`club_2122`, `club_2526`). |
| `team_code` | VARCHAR(3) | FK to `dim_team`. National team for tournament rows; NULL for club rows (where the team is a club, not a national team). |
| `club_name` | VARCHAR | For club-grain rows; NULL for tournament rows. |
| `minutes` | INTEGER | Total minutes played in this period. |
| `goals` | INTEGER | Goals in this period. |
| `xg_total` | DOUBLE | Total xG across the period. |
| `xg_per_90` | DOUBLE | xG normalized per 90 minutes. |
| `xa_total` | DOUBLE | Total expected assists (Understat only; NULL for StatsBomb when not available). |
| `xa_per_90` | DOUBLE | xA per 90. |
| `shots` | INTEGER | Total shots. |
| `as_of_date` | DATE | Build date — when this fact row was last computed. |

### `curated.fact_team_rating`

- **Grain:** one row per `(team_code, model_id, as_of_date)`.
- **Primary key:** `(team_code, model_id, as_of_date)`.
- **Source SQL:** unpivot `raw.team_ratings_all_models` (columns `M1_History`, `M2_Season`, `M3_RecentForm` → long form) plus separate inserts from `raw.team_attack_ratings` and `raw.team_defensive_ratings` with their respective `model_id`s.
- **FK constraints:**
  - `team_code` exists in `dim_team`
  - `model_id` exists in `dim_model`
- **Columns:**

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `model_id` | VARCHAR | FK to `dim_model`. Maps from `M1_History` → `m1-history`, etc. Hand-maintained mapping until model dirs catch up. |
| `as_of_date` | DATE | Build date. |
| `rating_value` | DOUBLE | The raw rating. |
| `rating_type` | VARCHAR | `'composite'`, `'attack'`, `'defense'`, `'historical'`, `'season'`, `'recent_form'`. |
| `confidence` | VARCHAR | `'high'`, `'medium'`, `'low'`. Defaults to `'medium'`. |

**Note:** The `raw.team_ratings_all_models` columns `M1_*`, `M2_*`, `M3_*` don't yet have matching `model_id` rows in `dim_model` (those are project-internal rating layers, not the named models like `elo-baseline`). For v1, the build script registers these as `model_id` entries automatically (e.g., `m1-history`, `m2-season`, `m3-recent-form`) or `model_id` is left NULL and the rating-source identification is on `rating_type`. Decided at implementation: NULL is simpler.

---

## Quarantine — `quarantine.*`

Every raw stats row that failed to match `dim_player` lands in `quarantine.unmatched_<source>` with full row contents plus:

| Column | Type | Description |
|---|---|---|
| `match_reason` | VARCHAR | `no_match`, `ambiguous_tier1_N`, `ambiguous_tier2_N`, `ambiguous_tier3_N`. |
| `candidate_player_ids` | VARCHAR | Comma-separated `player_id`s when ambiguous; empty otherwise. |
| `as_of_date` | DATE | Build date. |

**Tables built (v1):**
- `quarantine.unmatched_sb_player_summary`
- `quarantine.unmatched_sb_player_stats_pedigree`
- `quarantine.unmatched_understat_player_xg`
- `quarantine.unmatched_understat_2526_players`

**Expected v1 quarantine sizes (rough bounds for verification):**
- StatsBomb: ~10-25% quarantined initially (historical players not in WC2026 squads — expected, not pathological).
- Understat: ~50-70% quarantined initially (universe is much larger than WC2026 — most players never make a national team squad).

These bounds shrink over time as `dim_player.statsbomb_name` / `understat_id` columns get populated.

---

## Identity decisions (canonical)

- **Team identity:** FIFA 3-letter code (`MEX`, `ARG`, `BRA`). Natural key. Source: `tools/weekly_pull.py:NAME_TO_FIFA3` (and `ISO2_TO_FIFA3`).
- **Player identity:** Surrogate key `player_id` in format `P######`. Assigned at master ingest. Never reused, never reassigned.
- **Tournament identity:** Short slug (`wc2026`, `wc2022`, `euro2024`). Hand-curated.
- **Model identity:** Slug from `results/` directory name (`elo-baseline`, `ensemble-v2`). Auto-derived.

**Hard rule:** no analytical query downstream of the matching layer joins on player names. All joins use `player_id`, `team_code`, `tournament_id`, or `model_id`.

---

## Known data-quality gotchas (v1)

1. **DOB unavailable everywhere.** Tier 1 matching is dormant until roster master gains DOB (post ~Jun 4).
2. **No StatsBomb player IDs.** `raw.statsbomb_player_xg` has no internal player ID column we can persist. Matching relies on name + country only.
3. **Understat has stable `player_id`s — use them.** Persist on `dim_player.understat_id` for Tier 0 matching.
4. **Club rows have no nationality (mostly).** `raw.understat_player_xg` has a `nationality` column; `raw.understat_2526_players` does not. For 2526, Tier 2 falls back to fuzzy name + club match (Tier 3).
5. **Naming conventions differ across sources** (sampled in `python3 tools/inspect_parquets.py --player-names`):
   - StatsBomb: full legal names (`"Henry Josué Martín Mex"`, `"Cristiano Ronaldo dos Santos Aveiro"`).
   - Understat: common-use names (`"Donny van de Beek"`, `"Junya Ito"`).
   - squad_xg_ratings: aligned with StatsBomb-style formal names.
   - Implication: `rapidfuzz.token_set_ratio` handles the "long vs. short name" case well (intersection-based scoring).
6. **Roster JSON is currently empty.** `data/raw/squads/wc2026_squads_confirmed.json` only contains a "pending" country list, no player records. v1 uses `squad_xg_ratings.parquet` as the player-master source. Refresh tool is built to switch sources when JSON populates.
7. **Confederations not in the project today.** `db/masters/teams.csv` confederation column is hand-curated in Unit 2 (a small dict of 6 confederation → list of countries).
8. **`raw.team_ratings_all_models` has model columns (`M1_History`, `M2_Season`, `M3_RecentForm`) that aren't named models in `results/`.** Handled by allowing `fact_team_rating.model_id` to be NULL when the rating comes from an internal-only model layer; `rating_type` is used to identify the layer.

---

## Out-of-scope for v1 (deferred to separate plans)

- **Market snapshots** (`kalshi_snapshot_*.csv`, `polymarket_snapshot_*.csv`) → `fact_market_price`. Different ingestion cadence and schema.
- **Model predictions** (`results/<model>/<date>/predictions.csv`) → `fact_prediction`. Wide and varies by model; deserves its own consolidation pass.
- **Match-level facts** (`fact_match` from FIFA fixture list). Requires fixture pull script.
- **Comparison outputs** (`results/comparisons/*/comparison.csv`) → `fact_comparison`. Depends on `fact_prediction` first.
- **Live in-tournament data refresh** (Sofascore / API-Football pull from ~Jun 4) — see `MEMORY.md` → `wc2026_live_pipeline_plan.md`. The refresh tool built in this plan is the mechanism for picking that up.

---

## Verification (Unit 6 reference)

The verify script (`tools/verify_duckdb.py`) runs these assertion categories:

- **Row count ranges** on each curated table (bounds in this doc).
- **No-NULL on PK columns** of every curated table.
- **FK integrity:** every `fact_player_xg.player_id` exists in `dim_player`; every `fact_team_rating.team_code` exists in `dim_team`; every non-NULL `model_id` exists in `dim_model`.
- **Registry hygiene:** no duplicate `(normalized_name, country_code, birth_year)` in `dim_player` for `is_active = true` rows; all `player_id` values match `P######` format and are unique.
- **Source coverage:** every expected `raw.*` table is non-empty (drift sentinel).
- **Quarantine surface:** WARN (not FAIL) when any `quarantine.unmatched_*` table is non-empty, with row count.
- **Match rate floor:** WARN if `staging.matched_<source>` rate < 50% (drift sentinel).
