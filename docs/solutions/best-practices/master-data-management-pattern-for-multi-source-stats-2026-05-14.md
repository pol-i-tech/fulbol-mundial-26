---
title: Master-Data-Management Pattern for Multi-Source Player and Team Identity
date: 2026-05-14
category: docs/solutions/best-practices
module: duckdb-analytics-database
problem_type: best_practice
component: database
severity: high
applies_when:
  - Modeling dimensions and facts from multiple third-party stats sources (StatsBomb, Understat, Sofascore, FBref) that lack a shared canonical ID
  - Adding a new stats source to the WC2026 / fulbol-mundial-26 analytics pipeline
  - Tempted to derive `dim_player` (or any dim) by unioning + fuzzy-matching the source tables themselves
  - Building DuckDB curated views or fact tables that downstream analytical queries will join against
  - A new contributor needs to understand why entity resolution lives in `tools/match_sources_to_masters.py` and not in fact SQL
related_components:
  - tooling
  - documentation
tags:
  - master-data-management
  - duckdb
  - data-modeling
  - entity-resolution
  - dim-fact
  - parquet
  - sports-analytics
  - schema-design
---

# Master-Data-Management Pattern for Multi-Source Player and Team Identity

## Context

The `fulbol-mundial-26` repo ingests player and team performance data from at least three sources that all spell the same person differently:

- **StatsBomb** WC2022 + qualifier parquets call him `Harry Kane` (display string from open-data JSON), and `Lionel Messi` is `Lionel Andrés Messi Cuccittini` (full legal name).
- **Understat** EPL/league parquets use short common-use names (`Donny van de Beek`), but their primary key is an integer `player_id` and the slug is a normalized lowercased form.
- **Squad parquet** (`data/derived/squad_xg_ratings.parquet`, derived from the WC2026 squad scrape) carries FIFA-style display names — and is currently the closest thing to an authoritative roster pending the official Jun 4 release.
- Diacritics differ across sources (`Lautaro Martínez` vs `Lautaro Martinez`), name length differs (`Cristiano Ronaldo` vs `Cristiano Ronaldo dos Santos Aveiro`), and Understat club rosters contain ~5,000 players, most of whom will never see WC2026.

The tempting shortcut — `JOIN ON LOWER(player_name)` at query time, with a fuzzy fallback if no match — was explicitly considered and rejected during the v1 DuckDB build planning. The MDM pattern below is what replaced it.

## Guidance

### 1. Discovery is authoritative; matching is a load-time concern

Your dim is built from a roster source you trust, **not** by unioning distinct names across stats sources. Concretely: `db/masters/players.csv` is seeded from the current best squad source (`data/derived/squad_xg_ratings.parquet` today; `data/raw/squads/wc2026_squads_confirmed.json` once FIFA finalizes squads). Every `raw.statsbomb_*` and `raw.understat_*` row is matched into that universe at ETL time by `tools/match_sources_to_masters.py`.

New players never enter `dim_player` by appearing in a stats parquet — only by appearing in an updated master CSV. This separates "who exists in our universe" (a roster decision) from "what stats do we have about them" (a matching decision).

### 2. Assign opaque surrogate keys; never reuse them

Format: `P######` (zero-padded sequential). `P000001` is `P000001` forever, even if Understat changes the spelling, even if the player switches confederation. Master refresh (`tools/refresh_player_master.py`) matches incoming roster rows against existing `dim_player` rows on `(normalized_name, country_code, birth_year)` to preserve the assignment; only genuinely new identities get a new `P######`. Surrogate keys are committed to git via `db/masters/players.csv`, so the assignment is reproducible across machines and across DB rebuilds.

### 3. Resolve every raw stats row through a four-tier matching ladder

In order, implemented in `tools/match_sources_to_masters.py`:

- **Tier 0** — cached source ID lookup (e.g., `dim_player.understat_id`). Gold standard once seeded.
- **Tier 1** — exact `(normalized_name, country_code, birth_year)`. Dormant in v1 because no source carries DOB yet, but the column exists for forward compatibility (rosters carry DOB; we'll have it after the Jun 4 refresh).
- **Tier 2** — exact `(normalized_name, country_code)`. The primary deterministic key today.
- **Tier 3** — exact `(normalized_name, current_club)` for rows missing country (Understat club tables).
- **Tier 4** — `rapidfuzz.token_set_ratio >= 90`, constrained to candidates sharing country or current club. Below 90, the row is quarantined.

`token_set_ratio` was chosen specifically because it handles the long-name-vs-short-name case (`Lionel Andrés Messi Cuccittini` ↔ `Lionel Messi` scores 100 because the intersection equals the shorter string's full token set).

### 4. Facts are matched to dims, never the other way around

`curated.fact_player_xg` carries `player_id` as a FK to `curated.dim_player`. A stats row never extends the player universe by appearing. If a StatsBomb xG row cannot be matched, it lands in `quarantine.unmatched_<source>` with a `match_reason` column (`no_match`, `ambiguous_tier2_2`, etc.) — visible, queryable, reviewable. The 50% match rate on historical StatsBomb tournament data (`sb_player_stats_pedigree`) is by design: those are players from WC2018/Euro2020 who are not in the WC2026 universe.

### 5. Cache the source-specific name and ID back onto the master so matching compounds

Once Tier 4 fuzzy-matches `Bruno Borges Fernandes` (StatsBomb) to `P000830` `Bruno Miguel Borges Fernandes`, the match script writes `statsbomb_name=Bruno Borges Fernandes` and (for Understat sources) `understat_id=` back to `db/masters/players.csv`. The next ETL run resolves that row via Tier 0 (or Tier 2 hit on the cached spelling) in O(1) — no fuzzy match needed, no threshold risk. On the first build, 510 Understat rows matched via Tier 3/4; the second build hit Tier 0 for 577 of them via cached IDs. **Matching strength monotonically increases as the pipeline runs.**

### 6. Downstream analytics JOIN only on surrogate keys or canonical natural keys

`player_id` for people; `team_code` (FIFA 3-letter: `ARG`, `ENG`, `FRA`) for teams; `tournament_id` (`wc2026`, `euro2024`) for tournaments; `model_id` (slug from `results/<dir>/`) for models. Every analytical query in `db/queries/examples/` JOINs on these keys; there is no `LOWER(name) = LOWER(name)` anywhere in the curated layer. If you find yourself writing a name-based JOIN downstream of `staging.*`, you've broken the contract.

## Why This Matters

The union-the-distinct-names alternative has three failure modes that compound:

- **Discovery/matching conflation.** "Who exists in WC2026?" gets answered by "whoever has a stats row." When Understat publishes a 2026 player who hasn't been called up, they enter `dim_player`. When a confirmed squad player has no club minutes (injury, just promoted), they don't. The analytical surface drifts from the real-world roster.
- **Messy joins in every query.** Every analyst has to re-derive normalization rules, fuzzy thresholds, and tiebreakers. The xG-by-country query and the form-vs-rating query disagree on whether `Lautaro Martínez` and `Lautaro Martinez` are the same person.
- **Source-dependent universe.** If Understat changes a slug or rate-limits a fetch, players silently disappear from queries downstream. The data quality issue is invisible — there's no quarantine, just absent rows.

The MDM pattern inverts all three: the universe is fixed by the roster, matching happens once at load time with explicit tier provenance, and unmatched rows are visible in `quarantine.*`. The compounding benefit is the real payoff — every fuzzy match learned today becomes a Tier 0/2 exact match tomorrow, so accuracy monotonically increases as the pipeline runs rather than re-rolling the dice on every query.

## When to Apply

Apply MDM when:

- Adding a new dim source (e.g., a transfer-history feed that introduces a `transfer_id` per player — match it into `dim_player` and cache the ID).
- Adding a new stats source that needs `player_id` (Sofascore live xG when `pull_wc2026_live.py` comes online around Jun 4 — see `wc2026_live_pipeline_plan.md` in memory).
- Writing any cross-source analytical query (StatsBomb international xG + Understat club xG = composite player rating).
- Backfilling historical tournaments where players appear in multiple WC cycles.

Do **not** apply MDM when:

- **The natural key is already canonical and public.** Teams use FIFA 3-letter codes (`ARG`, `ENG`) directly as the primary key in `curated.dim_team`. There is no `T######` surrogate, because there's nothing to disambiguate — `ARG` is `ARG` everywhere. Adding a surrogate would be ceremony without benefit.
- **The dim is a tiny enumerated set authored by hand.** `curated.dim_tournament` (6 rows) and `curated.dim_model` (4 rows) use the slug itself as the key. Surrogate keys would add friction without preventing any real ambiguity.

## Examples

### Anti-pattern: fuzzy-name JOIN at query time

```sql
-- DON'T do this
SELECT sb.player, sb.xg AS xg_intl, u.total_xg AS xg_club
FROM raw.statsbomb_player_xg sb
JOIN raw.understat_player_xg u
  ON LOWER(TRIM(sb.player)) = LOWER(TRIM(u.player))
 AND sb.team = u.nationality
-- Bruno Borges Fernandes vs Bruno Fernandes: silently missed.
-- Lautaro Martínez vs Lautaro Martinez: depends on collation.
-- Every analyst reinvents these rules. No quarantine of misses.
-- Re-running may resolve differently if a source changes a spelling.
```

### MDM pattern: `player_id`-keyed join through curated dim

```sql
-- DO this
SELECT
    p.display_name,
    p.country_code,
    SUM(CASE WHEN f.source = 'statsbomb' THEN f.xg_total END) AS xg_intl,
    SUM(CASE WHEN f.source = 'understat' THEN f.xg_total END) AS xg_club,
    SUM(f.xg_total) AS xg_total_all_sources
FROM curated.fact_player_xg f
JOIN curated.dim_player p USING (player_id)
GROUP BY 1, 2
ORDER BY xg_total_all_sources DESC
LIMIT 10;

-- Harry Kane: 123 total xG. Lewandowski: 95. Lautaro: 76.
-- All disambiguation done once, at load time. Stable across rebuilds.
```

### Load-time matching tier ladder (algorithm shape)

From `tools/match_sources_to_masters.py`:

```python
def resolve_player_id(row, dim_player):
    # Tier 0: cached source ID (gold standard)
    if row.understat_id and (hit := dim_player.by_understat_id(row.understat_id)):
        return hit.player_id, "tier0_cached_understat_id"

    n = normalize(row.player_name)  # NFKD, strip diacritics, lower, collapse ws

    # Tier 1: name + country + birth_year (dormant; no DOB in v1 sources)
    if row.birth_year:
        if hit := dim_player.by(n, row.country_code, row.birth_year):
            return hit.player_id, "tier1_name_country_dob"

    # Tier 2: name + country (primary deterministic key today)
    if hit := dim_player.by(n, row.country_code):
        return hit.player_id, "tier2_name_country"

    # Tier 3: name + current_club (country missing)
    if hit := dim_player.by(n, club=row.current_club):
        return hit.player_id, "tier3_name_club"

    # Tier 4: fuzzy, constrained to shared country or club
    candidates = dim_player.filter(country=row.country_code) \
                 or dim_player.filter(club=row.current_club)
    best = max(candidates, key=lambda c: token_set_ratio(n, c.normalized_name))
    if best and token_set_ratio(n, best.normalized_name) >= 90:
        return best.player_id, "tier4_fuzzy"

    return None, "quarantine_no_match"  # -> quarantine.unmatched_*
```

After resolution, the script writes `row.source_name` and any source-side ID back to `db/masters/players.csv` so the next run hits Tier 0/2.

## Related

**Implementation references:**
- `db/SCHEMA.md` — full schema documentation (raw / curated / staging / quarantine).
- `db/README.md` — operational doc: build, verify, refresh masters, triage quarantine.
- `db/masters/players.csv` — the player master with surrogate keys and cached source names.
- `tools/match_sources_to_masters.py` — tier ladder implementation, quarantine writer, master-cache feedback loop.
- `tools/refresh_player_master.py` — master refresh with `player_id` preservation across runs.
- `tools/build_duckdb.py` — orchestrator assembling `data/wc2026.duckdb` end-to-end.
- `tools/verify_duckdb.py` — 27 assertions covering match rates, FK integrity, quarantine bounds.
- `db/queries/examples/top_scorers_blended_xg.sql` — canonical example of the `player_id` cross-source JOIN.

**Planning lineage** (chronological):
- `docs/plans/2026-05-06-world-cup-player-data-acquisition-strategy.md` — predecessor; proposed a Layer 1 player registry as a derived parquet with `player_id` + `identity_confidence`. Storage model superseded by this MDM doc (committed CSV master at `db/masters/players.csv` instead).
- `docs/plans/2026-05-06-player-data-gap-plan.md` — predecessor; specified `player_name_overrides.csv` and warned against burying overrides in fuzzy-match code. Aligned in spirit with MDM; the override mechanic is now the registry CSV itself.
- `docs/plans/2026-05-13-001-feat-build-duckdb-database-curated-models-plan.md` — **direct origin plan**. Contains the full Key Technical Decisions block. This learning is the institutional crystallization of that plan.

**Cross-references in the project:**
- `DEVELOPMENT.md` § "Analytics database (DuckDB)" — points to `db/README.md` and `db/SCHEMA.md`.
- `docs/agents/03-data-cleaning.md` — owns name normalization and player matching; should reference this pattern.
- `docs/agents/data-gaps-roadmap.md` Layer 1 — the "No canonical `player_registry.parquet`" gap is closed by the masters approach documented here.

**Auto memory:**
- `feedback_player_identity_registry.md` — the persistent decision record that informed this pattern. (auto memory [claude])
