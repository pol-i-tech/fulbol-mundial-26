# db/SCHEMA.md — DuckDB Analytics Database Schema

**Status:** active design (v1); committed before any DDL is written.
**Plan:** [docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md](../docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md)

This document is the contract for the DuckDB database at `data/wc2026.duckdb`. It specifies the four authoritative masters, the raw load layer, the curated dim/fact layer, the source-to-master matching algorithm, and the quarantine schema for unmatched rows.

**Design principle: master-data-management (MDM).** Every dim has an authoritative master source. Facts reference dims via stable surrogate keys (`player_id`) or canonical natural keys (`team_code`). Source stats are matched *to* the masters one-way; nothing extends a master from a fact source.

**Naming standard:** see [`db/NAMING.md`](NAMING.md) — applies to every `curated.*` and `staging.*` column documented in this file.

---

## Schemas (DuckDB namespaces)

| Schema | Purpose | Lifecycle |
|---|---|---|
| `raw` | 1:1 mirrors of `data/derived/*.parquet`. No transformations. | `CREATE OR REPLACE TABLE` on every build. |
| `curated` | Authoritative dims (`dim_*`) and analytical facts (`fact_*`). | `CREATE OR REPLACE TABLE` on every build. |
| `staging` | Intermediate per-source tables produced by the matching layer (raw stats with `player_id` resolved). | `CREATE OR REPLACE TABLE` on every build. |
| `quarantine` | Raw stats rows that failed to match a master, with `reason` column. | `CREATE OR REPLACE TABLE` on every build. |

---

## Curated Schema Quick Reference

The `curated.*` namespace is the **only** surface analytical code and models should read from. Everything below is built fresh on every `tools/build_duckdb.py` run; nothing here is hand-maintained state (the masters under `db/masters/*.csv` are). Row counts are as of 2026-05-15.

| Name | Type | Grain | PK / natural key | Purpose | Canonical read query |
|---|---|---|---|---|---|
| `curated.dim_team` | dim | one row per international team | `team_code` (FIFA3) | Team master: name, ISO2, confederation, WC2026 qualifier flag. ~98 rows. | `SELECT * FROM curated.dim_team WHERE is_wc2026_qualifier;` |
| `curated.dim_player` | dim | one row per player | `player_id` (`P######`) | Player master: canonical names, country, position, club, source-ID caches. ~1,274 rows. | `SELECT * FROM curated.dim_player WHERE country_code = 'ARG';` |
| `curated.dim_tournament` | dim | one row per tournament | `tournament_id` (slug) | Tournament master: window, host, type. 6 rows. | `SELECT * FROM curated.dim_tournament;` |
| `curated.dim_model` | dim | one row per model | `model_id` (slug) | Model master, auto-derived from `results/<model>/MODEL.md`. ~5 rows. | `SELECT * FROM curated.dim_model;` |
| `curated.dim_tournament_tier_weight` | dim | one row per tournament tier | `tournament_tier` | **Single source of truth for tier→weight priors.** Models that weight matches by importance JOIN this dim — never hardcode the weights. 4 rows. | `SELECT * FROM curated.dim_tournament_tier_weight;` |
| `curated.dim_team_current` | **view** | one row per team | `team_code` | Denormalized `dim_team` + latest economics + current FIFA rank. **Use this, not the underlying facts, for model reads.** | [`db/queries/examples/team_features_for_modeling.sql`](queries/examples/team_features_for_modeling.sql) |
| `curated.dim_team_recent_form` | **view** | one row per team | `team_code` | Last-5 / last-10 / competitive-last-10 form features plus strength-of-schedule. **Canonical form read.** | [`db/queries/examples/team_form_for_modeling.sql`](queries/examples/team_form_for_modeling.sql) |
| `curated.fact_international_match` | fact | one row per completed international match | (`match_date`, `home_team_code`, `away_team_code`) | All international results 1872→present, FIFA3-coded both sides, with `tournament_tier` and `neutral_site`. ~23k rows; ~3.5k since 2018. | [`db/queries/examples/team_recent_results.sql`](queries/examples/team_recent_results.sql) |
| `curated.fact_team_economics` | fact | one row per (team, year) | (`team_code`, `year`) | World Bank GDP per capita + population. Joined into `dim_team_current` for the latest year. ~1.9k rows. | `SELECT * FROM curated.fact_team_economics WHERE team_code = 'BRA' ORDER BY year DESC;` |
| `curated.fact_team_fifa_ranking` | fact | one row per team (current snapshot) | `team_code` | Single FIFA ranking snapshot — rank, points, rank_change. Joined into `dim_team_current`. 48 rows. | `SELECT * FROM curated.fact_team_fifa_ranking ORDER BY rank;` |
| `curated.fact_team_rating` | fact | one row per (team, rating_type) | (`team_code`, `rating_type`, `as_of_date`) | Unpivoted internal team ratings: `historical`, `season`, `recent_form`, `attack`, `defense`. Point-in-time snapshot. ~244 rows. | [`db/queries/examples/attack_vs_defense_per_team.sql`](queries/examples/attack_vs_defense_per_team.sql) |
| `curated.fact_player_xg` | fact | one row per (player, source, period) | (`player_id`, `source`, `period_id`) | Blended xG totals per player across StatsBomb tournaments and Understat club seasons. ~2.5k rows. | [`db/queries/examples/top_scorers_blended_xg.sql`](queries/examples/top_scorers_blended_xg.sql) |
| `curated.fact_player_xg_per_90` | fact | one row per player | `player_id` | Per-player blended xG/xA per 90, with separate club and national-team components. Built from `raw.squad_xg_ratings`. 1,274 rows. | `SELECT * FROM curated.fact_player_xg_per_90 WHERE team_code = 'ARG' ORDER BY blended_xg_per_90 DESC;` |
| `curated.fact_team_xg` | fact | one row per team | `team_code` | **Squad-aggregate xG per 90 — top-11-by-national-minutes (likely XI) summed.** Includes forwards-only and top-3-attacker variants plus a club-data-coverage flag. 52 rows. | [`db/queries/examples/team_xg_for_modeling.sql`](queries/examples/team_xg_for_modeling.sql) |
| `curated.fact_team_xg_against` | fact | one row per team | `team_code` | **Squad-aggregate xGA per 90.** National signal (avg opponent xG across 5 SB tournaments) + squad-club signal (minutes-weighted club xGA via player's current_club). 98 rows; 59 with non-null blend. | [`db/queries/examples/team_xga_for_modeling.sql`](queries/examples/team_xga_for_modeling.sql) |
| `curated.fact_team_xg_against_wc2022` | fact | one row per WC2022 team | `team_code` | **Point-in-time WC2022-cut defensive xGA** for honest held-out backtest. Sourced from `raw.team_defense_ratings_wc2022`. 32 rows. | `SELECT * FROM curated.fact_team_xg_against_wc2022 ORDER BY pre_wc2022_blended_xga_per_90;` |

**Read discipline:** Prefer the two `dim_team_*` views over the underlying facts whenever a model needs per-team features. They're the project's denormalized read path — one query, every feature, no JOIN bookkeeping for the modeler. The per-fact tables are still the right read when you need history (`fact_team_economics` for the time series, `fact_international_match` for per-match analysis).

**More examples:** see [`db/queries/examples/`](queries/examples/) for the full catalogue — `model_agreement_matrix.sql`, `squad_coverage_gaps.sql`, `inspect_quarantine.sql`, etc.

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

### `db/masters/tournament_tier_weights.csv` — the tier-weight master

**Primary key:** `tournament_tier` (the same slug used by `curated.fact_international_match.tournament_tier`).

**Source provenance:** hand-curated. Tiny enumeration table. **The single source of truth for the per-tier match-importance weight applied by every model that weights matches by competition.** Modeling code does not hardcode these values — it JOINs `curated.dim_tournament_tier_weight`.

**Columns:**

| Column | Type | Description |
|---|---|---|
| `tournament_tier` | VARCHAR | One of `tier_1_world_cup`, `tier_2_continental_final`, `tier_3_qualifier_or_nations_league`, `tier_4_friendly_or_other`. Must agree with the set produced by `curated.fact_international_match`. |
| `weight` | DOUBLE | Per-tier weight in `(0, 1]`. Tier 1 is the reference. Verified by `tools/verify_duckdb.py`. |
| `rationale` | VARCHAR | One-sentence justification. |

**Cardinality:** 4 rows. Adding a new tier requires updating this master *and* the `tournament_tier` CASE inside `db/sql/curated/fact_international_match.sql` in the same PR — otherwise the verifier's coverage assertion will fail.

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
| `international_matches.parquet` | `raw.international_matches` | ~49,300 | per match (1872–present) | Derived from `data/raw/martj42/latest/results.csv` by `tools/derive_international_matches.py`. Both team names pre-resolved to FIFA3 via `normalize_country()`. |

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

### `curated.fact_player_xg_per_90`

Per-player blended xG/xA per 90, with the club component and national-team component preserved separately for downstream re-mixing.

- **Grain:** one row per `player_id` (1:1 with `dim_player`).
- **Primary key:** `player_id`. Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_player_xg_per_90.sql`. Joins `raw.squad_xg_ratings` to `curated.dim_player` on `(display_name, nation_name)` — a 1:1 match because `dim_player` was built from `squad_xg_ratings` upstream.
- **FK constraints:** `player_id` exists in `dim_player`; `team_code` exists in `dim_team`.
- **Cardinality:** ~1,274 rows.

| Column | Type | Description |
|---|---|---|
| `player_id` | VARCHAR | FK to `dim_player`. |
| `team_code` | VARCHAR(3) | FK to `dim_team`. The player's national team. |
| `position` | VARCHAR | Free-form (e.g., `"F"`, `"F M S"`). Carried from `squad_xg_ratings`. |
| `current_club`, `current_league` | VARCHAR | Club + league at squad-pool time. |
| `national_team_matches`, `national_team_minutes` | INTEGER | National-team usage. |
| `national_team_xg_per_90` | DOUBLE | StatsBomb national-team xG normalised per 90. |
| `national_team_shots_per_90`, `national_team_key_passes_per_90`, `national_team_prog_passes_per_90`, `national_team_prog_carries_per_90`, `national_team_pressures_per_90` | DOUBLE | Other StatsBomb per-90 rates (for downstream models that want more than xG). |
| `club_minutes` | INTEGER | 2024–25 Understat club minutes. |
| `club_xg_per_90`, `club_xa_per_90` | DOUBLE | Understat club rates. NULL if league not in Understat (e.g., MLS, Brazilian Série A, Saudi Pro League). |
| `blended_xg_per_90` | DOUBLE | Pre-blended club+national xG per 90 (upstream pipeline owns the blend). |
| `found_in_understat` | BOOLEAN | TRUE if club xG was resolvable. |
| `low_confidence` | BOOLEAN | TRUE when nat or club sample is too small for the per-90 rate to be stable. |
| `as_of_date` | DATE | Build date. |

---

### `curated.fact_team_xg`

Team-aggregate xG per 90, derived from `fact_player_xg_per_90`. The headline model-facing metric is `top_11_blended_xg_per_90`.

- **Grain:** one row per `team_code` (the 52 nations with squad-pool data; not all `dim_team` rows have squad data).
- **Primary key:** `team_code`. Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_team_xg.sql`. Three sub-aggregations: top-11 by national-team minutes, forwards-only (position contains `F`), top-3 attackers, full pool average.
- **FK constraints:** `team_code` exists in `dim_team`.
- **Model-facing read pattern:** use `top_11_blended_xg_per_90` as the squad-attack signal. Pair with `club_data_coverage_percent` to decide whether to trust the club-component split for that team (Brazil, Uruguay, Ecuador have < 40% Understat coverage because their domestic leagues are not in Understat).
- **Aggregation math:** per-90 rates sum across a starting XI to give the team's expected per-match goal output. Sum-of-top-11 is a coarse proxy for "expected starting XI" pending real lineup data; the alternative aggregations let a modeler tune.
- **Cardinality:** 52 rows.

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `team_name`, `confederation`, `is_wc2026_qualifier` | varies | Carried from `dim_team` for read convenience. |
| `players_in_pool` | BIGINT | Count of `fact_player_xg_per_90` rows for this team. |
| `players_with_club_data` | BIGINT | Subset of pool with `found_in_understat = TRUE`. |
| `club_data_coverage_percent` | DOUBLE | `players_with_club_data / players_in_pool * 100`. Low values flag unreliable club components. |
| `top_11_blended_xg_per_90` | DOUBLE | **Primary metric.** SUM of `blended_xg_per_90` over the 11 players with the most national-team minutes. |
| `top_11_national_team_xg_per_90` | DOUBLE | SUM of `national_team_xg_per_90` for the same 11. |
| `top_11_club_xg_per_90`, `top_11_club_xa_per_90` | DOUBLE | SUM of `club_xg_per_90` / `club_xa_per_90` for the same 11. NULL-suppressed by SUM, so coverage gaps show up as a low value rather than a NULL. |
| `top_11_national_team_minutes` | INTEGER | Sample-size basis for the top-11 selection. |
| `forwards_in_pool` | BIGINT | Count of players whose `position` contains `'F'`. |
| `forwards_blended_xg_per_90` | DOUBLE | SUM over forwards. |
| `forwards_avg_blended_xg_per_90` | DOUBLE | AVG over forwards. |
| `top_3_attackers_blended_xg_per_90` | DOUBLE | SUM of the top-3 forwards by `blended_xg_per_90`. The "front line" view. |
| `all_pool_avg_blended_xg_per_90` | DOUBLE | AVG over the whole squad pool. |
| `total_national_team_minutes`, `total_club_minutes` | INTEGER | Pool-level minute totals. |
| `as_of_date` | DATE | Build date. |

**Caveat — Understat league coverage.** Brazilian Série A, MLS, Saudi Pro League, and other non-European leagues are not in Understat. Teams whose stars play in those leagues (Brazil, USA, Saudi Arabia, Mexico, parts of Belgium and Croatia) have `club_data_coverage_percent` below ~50%. For those teams, `top_11_blended_xg_per_90` leans more heavily on the national-team component, which is fine for international football modeling but worth noting when comparing teams across confederations.

---

### `curated.fact_team_xg_against`

Defensive sibling of `fact_team_xg`. Squad-aggregate xGA per 90 from two independent sources blended into one model-facing metric.

- **Grain:** one row per `team_code` (1:1 with `dim_team`).
- **Primary key:** `team_code`. Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_team_xg_against.sql`. Three CTEs: per-match xGA via self-join on `raw.statsbomb_team_xg` (opponent's `xg` becomes our `xga`); squad-weighted club xGA via `raw.defensive_ratings_club_2526` joined through `dim_player.current_club`; top-11 pressures-per-90 from `fact_player_xg_per_90`.
- **FK constraints:** `team_code` exists in `dim_team`.
- **Model-facing read pattern:** use `blended_xga_per_90` as the squad-defense signal. Pair with `national_team_matches_in_sample` (sample-size honesty) and `squad_players_with_club_xga` (club-coverage honesty). Use `national_team_xga_vs_actual_gap_per_90` to flag defenses that have been over/underperforming their underlying metrics — large positive gaps (Belgium +0.47, Brazil +0.45, England +0.56) are a luck-detection signal.
- **Blend:** 60% national + 40% club when both available; the single available source when only one is.
- **Cardinality:** 98 rows total (one per `dim_team`); 59 with non-null `blended_xga_per_90`.

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `team_name`, `confederation`, `is_wc2026_qualifier` | varies | Carried from `dim_team` for read convenience. |
| `national_team_matches_in_sample` | BIGINT | Match count across SB tournaments (WC18, WC22, Euro 2020, Euro 2024, Copa 2024). |
| `national_team_minutes_in_sample` | BIGINT | `matches × 90` approximation. |
| `national_team_xga_per_90` | DOUBLE | AVG of opponent's `xg` across SB matches. |
| `national_team_goals_conceded_per_90` | DOUBLE | AVG of actual goals conceded. |
| `national_team_xga_vs_actual_gap_per_90` | DOUBLE | `xga − actual`. Positive = defense overperforming (luck); negative = underperforming. |
| `squad_players_with_club_xga` | BIGINT | Count of squad players whose `current_club` is in `defensive_ratings_club_2526`. |
| `squad_club_xga_per_game` | DOUBLE | Minutes-weighted avg of those players' club `xga_per_game`. |
| `top_11_national_team_pressures_per_90` | DOUBLE | Pressures-per-90 summed over the top-11 by `national_team_minutes`. Activity proxy. |
| `blended_xga_per_90` | DOUBLE | **Primary metric.** 0.6 × `national_team_xga_per_90` + 0.4 × `squad_club_xga_per_game` when both available. |
| `sb_tournaments_in_sample` | VARCHAR | Comma-separated list of contributing SB competitions. |
| `as_of_date` | DATE | Build date. |

**Caveat — limited club coverage.** `raw.defensive_ratings_club_2526` only covers ~5 leagues (~96 clubs); most non-European leagues are absent. Teams whose squad plays largely outside those leagues will have low `squad_players_with_club_xga` and the blended metric will lean more on the national-team component.

**Caveat — small SB samples for some teams.** Iran, Qatar, Senegal, Scotland have fewer than 10 SB tournament matches in the sample. Their `national_team_xga_per_90` is statistically noisier. The `national_team_matches_in_sample` column makes this explicit.

---

### `curated.fact_team_xg_against_wc2022`

Point-in-time WC2022-cut defensive xGA. Holds team-level defensive ratings as of WC2022 kickoff — used by the WC2022 backtest harness so the defensive signal doesn't leak post-tournament data.

- **Grain:** one row per WC2022 team (the 32 nations that played).
- **Primary key:** `team_code`. Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_team_xg_against_wc2022.sql`. Projects `raw.team_defense_ratings_wc2022` (already pre-aggregated upstream as a point-in-time snapshot) with the same blending convention as `fact_team_xg_against`.
- **FK constraints:** `team_code` exists in `dim_team`.
- **Cardinality:** 32 rows.

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `team_name` | VARCHAR | Source nation name (carried from raw). |
| `pre_wc2022_defensive_rating` | DOUBLE | Upstream pipeline's defensive rating (one-number summary). |
| `pre_wc2022_tournament_xga_per_90` | DOUBLE | Tournament-level xGA per 90 as of pre-WC2022. |
| `pre_wc2022_club_xga_avg_per_game` | DOUBLE | Squad-weighted club xGA average as of pre-WC2022. May be NULL. |
| `pre_wc2022_club_sample_size` | BIGINT | Players whose club xGA contributed. |
| `pre_wc2022_used_fallback` | BOOLEAN | TRUE if the upstream pipeline had to fall back to a less-preferred xGA estimate (e.g., when the team had no SB-covered pre-WC2022 matches). |
| `pre_wc2022_blended_xga_per_90` | DOUBLE | 0.6 × tournament + 0.4 × club blend (same formula as the current-snapshot table). |
| `as_of_date` | DATE | Build date (NOT the snapshot date — the snapshot is implicitly pre-2022-11-20). |

**Read discipline:** This table is for the WC2022 backtest only. For current modeling, use `fact_team_xg_against`. All column names start with `pre_wc2022_` to make the temporal scope unmistakable at the join site.

---

### `curated.fact_team_economics`

Country-context macro features for model use. Built by plan [`2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md`](../docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md).

- **Grain:** one row per `(team_code, year)`.
- **Primary key:** `(team_code, year)`. Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_team_economics.sql`. CTE-first; `FULL OUTER JOIN raw.country_gdp_per_capita ⇄ raw.country_population` (so a (team, year) with only one measure still appears), then `LEFT JOIN curated.dim_team` and filter on `dim_team_code IS NOT NULL`. Unmatched rows route to `quarantine.unmatched_team_economics`.
- **FK constraints:** `team_code` exists in `dim_team`.
- **Coverage rule:** every WC2026 qualifier (except `SCO`) has a non-null measure for each of the 5 most-recent reported years. Window is computed dynamically as `[MAX(year) - 4 .. MAX(year)]` over rows with non-null measures, so it auto-shifts when World Bank publishes a new year.
- **Year range:** 1986–2025 (last fully-reported year at time of writing: 2024).

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `year` | INTEGER | 1986–2025 inclusive. |
| `gdp_per_capita_usd` | DOUBLE | World Bank `NY.GDP.PCAP.CD` (current US$). Nullable. |
| `population` | DOUBLE | World Bank `SP.POP.TOTL`. Nullable. |

**Scotland (SCO) exception:** Scotland has no World Bank entity (rolled into GBR upstream). Its rows are emitted with NULL measures and survive the FK filter so the time-series grain stays explicit — a `dim_team_current.gdp_per_capita_usd_latest = NULL` for Scotland is by design, and the modeler chooses whether to impute from GBR.

---

### `curated.fact_team_fifa_ranking`

- **Grain:** one row per `(team_code, snapshot_date)`. Currently latest-snapshot only.
- **Primary key:** `team_code` (single-snapshot grain). Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_team_fifa_ranking.sql`. CTE-first projection from `raw.fifa_world_ranking_current` (sourced from Wikipedia's `Module:SportsRankings/data/FIFA_World_Rankings`, the authoritative public mirror of the FIFA Men's World Ranking), `LEFT JOIN curated.dim_team`, filter on `dim_team_code IS NOT NULL`. Unmatched rows route to `quarantine.unmatched_team_fifa_ranking`.
- **FK constraints:** `team_code` exists in `dim_team`.
- **`CREATE OR REPLACE` semantics:** this fact holds the most recent FIFA ranking edition only. Historical accumulation lives in a future `fact_team_fifa_ranking_history` table (deferred).

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `rank` | INTEGER | Global FIFA rank (1 = top). |
| `points` | DOUBLE | Current FIFA ranking points. |
| `rank_change` | INTEGER | Change since the previous edition. |
| `snapshot_date` | DATE | FIFA's published edition date (falls back to fetched-at, then build-date). |
| `built_at` | TIMESTAMP | Build-time audit. |

---

### `curated.fact_international_match`

Match-level results for international football. Built by plan [`2026-05-15-001-feat-fact-international-match-plan.md`](../docs/plans/2026-05-15-001-feat-fact-international-match-plan.md).

- **Grain:** one row per completed international match.
- **Primary key:** `(match_date, home_team_code, away_team_code)`. Uniqueness enforced by `verify_duckdb.py`.
- **Source SQL:** `db/sql/curated/fact_international_match.sql`. CTE-first; LEFT JOIN `curated.dim_team` twice (once per team side), then split via `WHERE dim_home_code IS NOT NULL AND dim_away_code IS NOT NULL`. Unmatched rows route to `quarantine.unmatched_international_matches`.
- **FK constraints:** both `home_team_code` and `away_team_code` exist in `dim_team`.
- **Date range:** 1872-11-30 → most recent completed match in the martj42 weekly pull.
- **Future-fixture exclusion:** rows with `NULL` `home_score` or `away_score` in the source CSV are excluded — this fact holds RESULTS only.
- **Tournament tier scheme** (derived column, `VARCHAR`):
  - `tier_1_world_cup` — `tournament = 'FIFA World Cup'`
  - `tier_2_continental_final` — `UEFA Euro`, `Copa América`, `African Cup of Nations`, `AFC Asian Cup`, `Gold Cup`, `CONCACAF Championship`, `Oceania Nations Cup`, `Confederations Cup`
  - `tier_3_qualifier_or_nations_league` — any `*qualification*` plus `UEFA Nations League`, `CONCACAF Nations League`
  - `tier_4_friendly_or_other` — `Friendly`, regional cups, minor competitions, unclassified

| Column | Type | Description |
|---|---|---|
| `match_date` | DATE | Calendar date of the match. |
| `home_team_code` | VARCHAR(3) | FK to `dim_team`. |
| `away_team_code` | VARCHAR(3) | FK to `dim_team`. |
| `home_score` | INTEGER | Home team goals. |
| `away_score` | INTEGER | Away team goals. |
| `goal_difference` | INTEGER | `home_score - away_score`. |
| `result` | VARCHAR(1) | `'H'` (home win), `'A'` (away win), `'D'` (draw). |
| `tournament` | VARCHAR | Source competition string (free-form; ~200 distinct values). |
| `tournament_tier` | VARCHAR | Derived; see scheme above. |
| `is_competitive` | BOOLEAN | `tournament_tier <> 'tier_4_friendly_or_other'`. |
| `city` | VARCHAR | Host city. |
| `host_country` | VARCHAR | Host country (display name from source). |
| `neutral_site` | BOOLEAN | `TRUE` when the match was at neutral venue. |

---

### `staging.team_match`

The match-grain fact unpivoted to one row per team-perspective. Built by plan [`2026-05-15-001-feat-fact-international-match-plan.md`](../docs/plans/2026-05-15-001-feat-fact-international-match-plan.md).

- **Grain:** one row per `(team_code, match_date, opponent_team_code, venue)`. Each fact row contributes two staging rows.
- **Primary key:** `(team_code, match_date, opponent_team_code, venue)`. The `venue` component is required to disambiguate legitimate same-day double-headers (e.g., ARG vs URU on 1916-08-15 played both Copa Newton in Avellaneda AND Copa Lipton in Montevideo).
- **Source SQL:** `db/sql/staging/team_match.sql`. `UNION ALL` of home-perspective and away-perspective projections from `curated.fact_international_match`.
- **Row count:** exactly `2 * COUNT(fact_international_match)`.

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | FK to `dim_team`. |
| `opponent_team_code` | VARCHAR(3) | FK to `dim_team`. |
| `match_date` | DATE | |
| `team_score` | INTEGER | This team's goals. |
| `opponent_score` | INTEGER | Opponent's goals. |
| `goal_difference` | INTEGER | `team_score - opponent_score`. |
| `outcome` | VARCHAR(1) | `'W'` / `'D'` / `'L'` from this team's perspective. |
| `venue` | VARCHAR(1) | `'H'` (home), `'A'` (away), `'N'` (neutral). |
| `tournament` | VARCHAR | Carried from fact. |
| `tournament_tier` | VARCHAR | Carried from fact. |
| `is_competitive` | BOOLEAN | Carried from fact. |

---

### `curated.dim_team_recent_form` (VIEW)

Read-optimized per-team recent-form features. Built by plan [`2026-05-15-001-feat-fact-international-match-plan.md`](../docs/plans/2026-05-15-001-feat-fact-international-match-plan.md).

- **Grain:** one row per `team_code` (parity with `dim_team`).
- **Type:** `VIEW`, recomputes at query time.
- **Source SQL:** `db/sql/curated/dim_team_recent_form.sql`. Ranks `staging.team_match` rows per team by `match_date DESC`, computes per-team aggregates with `FILTER` clauses for two recency windows (last-5, last-10) and an independent competitive-only window. Strength-of-schedule joins `curated.fact_team_fifa_ranking` (snapshot ranks).
- **Two recency windows** (last-5, last-10) plus competitive-only variants. Competitive-only uses an independent rank window — a team whose recent 10 matches are 6 competitive + 4 friendlies has `competitive_matches_last_10` counted over the last 10 *competitive* matches (which may extend further back in calendar time).

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | From `dim_team`. |
| `team_name` | VARCHAR | From `dim_team`. |
| `last_match_date` | DATE | Date of most recent match. |
| `last_match_opponent_team_code` | VARCHAR(3) | |
| `last_match_outcome` | VARCHAR(1) | `'W'` / `'D'` / `'L'`. |
| `matches_last_10` | BIGINT | Match count in last 10. ≤ 10 — may be less for teams with fewer fact rows. |
| `wins_last_10` / `draws_last_10` / `losses_last_10` | BIGINT | Outcome counts. |
| `goals_for_last_10` / `goals_against_last_10` | INT128 | Goals for / against. |
| `goal_difference_last_10` | INT128 | `goals_for - goals_against`. |
| `form_points_last_10` | INT128 | `3*W + 1*D` over last 10. |
| `matches_last_5` ... `form_points_last_5` | various | Same set, narrower window. |
| `competitive_matches_last_10` | BIGINT | Match count in last 10 **competitive** matches. |
| `competitive_goal_difference_last_10` | INT128 | |
| `competitive_form_points_last_10` | INT128 | |
| `avg_opponent_fifa_rank_last_10` | DOUBLE | Average of opponent's current FIFA rank over last 10 matches. **Limitation:** uses snapshot ranks, not rank-at-time-of-match. Historical ranking is deferred. |
| `as_of_date` | DATE | Build-date stamp. |

---

### `curated.dim_team_current` (VIEW)

Denormalized read-optimized projection — the model-facing read path. One read, every team feature.

- **Grain:** one row per `team_code` (parity with `dim_team`).
- **Type:** `VIEW`, not `TABLE`. Zero storage, recomputes at query time, never goes stale.
- **Source SQL:** `db/sql/curated/dim_team_current.sql`. `dim_team` `LEFT JOIN` latest-economics (pre-filtered to rows with non-null measures, then `ROW_NUMBER() … = 1` by year DESC) `LEFT JOIN` current FIFA ranking. `LEFT JOIN` semantics preserve every dim row even when a fact is missing.

| Column | Type | Description |
|---|---|---|
| `team_code` | VARCHAR(3) | From `dim_team`. |
| `team_name` | VARCHAR | From `dim_team`. |
| `iso2_code` | VARCHAR(2) | From `dim_team`. |
| `confederation` | VARCHAR | From `dim_team`. |
| `is_wc2026_qualifier` | BOOLEAN | From `dim_team`. |
| `economics_year` | INTEGER | Year of the most-recent reported economics row (currently 2024). |
| `gdp_per_capita_usd_latest` | DOUBLE | GDP per capita for `economics_year`. |
| `population_latest` | DOUBLE | Population for `economics_year`. |
| `fifa_rank` | INTEGER | Current FIFA rank. |
| `fifa_points` | DOUBLE | Current FIFA ranking points. |
| `fifa_rank_change` | INTEGER | Change since previous edition. |
| `fifa_snapshot_date` | DATE | FIFA edition date. |

**Model-side usage:** filter by `is_wc2026_qualifier` and order by `fifa_rank`. See `db/queries/examples/team_features_for_modeling.sql`.

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
- `quarantine.unmatched_team_economics` — World Bank rows whose `team_code` is not in `dim_team`. Schema: `team_code, year, gdp_per_capita_usd, population, source, reason`. Built from the same CTE pipeline as `fact_team_economics`, opposite `WHERE` filter.
- `quarantine.unmatched_team_fifa_ranking` — FIFA ranking rows whose `team_code` is not in `dim_team`. Schema: `team_code, rank, points, rank_change, reason`.
- `quarantine.unmatched_international_matches` — martj42 match rows whose home or away team failed to resolve to `dim_team`. Schema: `match_date, home_team_name, home_team_code, away_team_name, away_team_code, home_score, away_score, tournament, reason`. The `reason` column distinguishes `home_unresolved` / `away_unresolved` / `both_unresolved` (normalize_country returned NULL) from `home_not_in_dim` / `away_not_in_dim` / `both_not_in_dim` (FIFA3 returned, not in dim_team). Expected row count is large (~26K out of ~49K source rows) because martj42 covers all FIFA members across 154 years; `dim_team` is scoped to WC2026-relevant teams.

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
- **Match-level fixtures** (`fact_international_fixture` — future-dated rows from the martj42 pull). Distinct from `fact_international_match`, which holds completed results. Deferred until the modeling layer needs scheduled fixtures.
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
