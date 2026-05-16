---
title: "feat: SQL nomenclature standard (columns, CTEs, aliases) and refactor of existing SQL"
type: feat
status: active
date: 2026-05-15
---

# feat: SQL nomenclature standard (columns, CTEs, aliases) and refactor of existing SQL

## Overview

Define and adopt a project-wide SQL nomenclature standard for `db/`, `db/queries/`, and `methodology/*/queries/`. The standard outlaws unclear short forms in **column names** and requires **complete words** for CTE names, table names, and join aliases. A small set of statistical abbreviations (`avg`, `std`, `mean`, `stats`) and domain acronyms (`xg`, `xa`, `fifa`, `gdp`, `iso2`, `usd`) are explicitly allowed.

This plan delivers two things in one PR:

1. A new conventions document (`db/NAMING.md`) that captures the standard.
2. A refactor of every SQL file currently in the repo that violates it — plus the one downstream Python consumer (`methodology/curated-poisson-luck/model.py`) and the affected docs.

After this lands, `gf`, `ga`, `gf_mean`, `gf_std`, `n_matches`, `w_sum`, `hist_*`, and single-letter join aliases (`a`, `c`, `f`, `g`, `tm`, `tw`, `rk`, `pt`, `lm`, `sos`) are no longer present in committed SQL. The CTE name `goal_stats` is kept — `stats` is an allowed short, on the same footing as `avg`/`std`/`mean`.

## Problem Frame

Recent SQL added under `db/queries/examples/` and `methodology/curated-poisson-luck/queries/` introduced short-form column names (`gf`, `ga`, `gf_mean`, `gf_std`, `ga_mean`, `ga_std`, `n_matches`, `w_sum`, `hist_gf_mean`, `hist_gf_std`, `hist_ga_mean`, `hist_ga_std`) and 1–2-character table aliases (`a`, `c`, `f`, `g`, `m`, `s`, `w`, `pt`, `tm`, `tw`, `rk`, `lm`, `sos`).

Two costs of letting this stand:

- **Onboarding.** A modeler reading `gf_mean` has to look up that `gf` = "goals for"; the column doesn't self-describe. Same for `n_matches` (count of matches), `w_sum` (sum of tier weights), `hist_*` (historical/since-2022 window).
- **Cross-file drift.** `gf_mean` appears in three different SQL files plus `db/SCHEMA.md` plus `methodology/curated-poisson-luck/README.md` plus the Python model. Each new model author has to memorize the dialect.

The fix is one-time and mechanical: agree on a standard, apply it across every committed SQL file, update the model consumer that reads the renamed columns, refresh docs.

## Requirements Trace

- **R1.** Column names in SQL never use unclear short forms. The only allowed statistical abbreviations are `avg`, `std`, `mean`, `stats`. Domain acronyms (`xg`, `xa`, `fifa`, `gdp`, `iso2`, `usd`) are allowed.
- **R2.** CTE names and table names use complete words — no abbreviations beyond the allowed statistical shorts in R1. So `goal_stats` stays (`stats` is allowed); `sos`, `hist`, `tmp`, `agg`, etc. do not.
- **R3.** Table/join aliases in SELECT/JOIN use complete words (or omit aliases) — no 1–2 character aliases like `a`, `tm`, `tw`.
- **R4.** Existing committed SQL files in `db/sql/`, `db/queries/`, and `methodology/*/queries/` are refactored to comply with the new standard.
- **R5.** Downstream consumers that read renamed columns (`methodology/curated-poisson-luck/model.py`, `methodology/curated-poisson-luck/README.md`, `db/SCHEMA.md`) are updated in the same PR so the build + verify scripts stay green.
- **R6.** `tools/verify_duckdb.py` continues to pass against the rebuilt database.

## Scope Boundaries

- **In scope.** Column aliases produced inside SQL (`AS`), CTE names, exposed view columns on `curated.*` and `staging.*`, downstream Python/Markdown references to renamed columns, the new `db/NAMING.md` standard.
- **Not in scope.** Renaming columns inside `data/derived/*.parquet` (raw layer ingests parquets 1:1; the rule applies the moment we transform them in `db/sql/curated/`). Renaming columns inside `db/masters/*.csv`. Renaming files. Renaming `dim_*` / `fact_*` table names — those already follow the convention.

### Deferred to Separate Tasks

- **Renaming master-CSV column names** (e.g., the `weight` column in `tournament_tier_weights.csv` is fine, but if any master uses `gf`/`ga`-style shorts in the future, it lands in a separate plan that also handles the CSV migration).
- **Auditing `data/derived/` parquet column names** for compliance — these are produced upstream of the curated layer and many are inherited from third-party sources (StatsBomb, Understat, FIFA, World Bank).
- **Linter or CI gate** that enforces the standard mechanically (e.g., a `tools/lint_sql_names.py`). Worth doing later; out of scope here.

## Context & Research

### Relevant Code and Patterns

- `db/SCHEMA.md` — current column documentation; will need updates for every renamed column on `dim_team_recent_form` and any other affected curated table.
- `db/sql/curated/dim_team_recent_form.sql` — exposes `gf_last_10`, `ga_last_10`, `gf_last_5`, `ga_last_5`, `goal_diff_last_10`, `goal_diff_last_5`, `competitive_goal_diff_last_10`, `competitive_form_points_last_10`. Also uses the alias `sos` (= strength of schedule) for a CTE.
- `db/sql/curated/fact_international_match.sql` — already produces `goal_diff` (committed). The standard's treatment of `goal_diff` vs `goal_difference` is one of the decisions below.
- `db/sql/staging/team_match.sql` — produces `goal_diff` (same column carried from `fact_international_match`).
- `db/queries/examples/team_goal_stats_for_modeling.sql`, `db/queries/examples/curated_poisson_luck_per_team_features.sql`, `db/queries/examples/team_recent_results.sql` — `gf`/`ga` inline aliases, `gf_mean`/`gf_std`, `n_matches`, `w_sum`, single-letter join aliases.
- `methodology/curated-poisson-luck/queries/team_goal_stats.sql` — canonical home of the goal-stats CTE (the `db/queries/examples/` ones are mirrors per existing comments).
- `methodology/curated-poisson-luck/queries/team_model_features.sql` — joins the goal-stats CTE; defines the `hist_gf_mean`/`hist_gf_std`/`hist_ga_mean`/`hist_ga_std` columns the model reads.
- `methodology/curated-poisson-luck/model.py` — reads `features["hist_gf_mean"]` directly. Renaming the column requires updating the model.
- `methodology/curated-poisson-luck/README.md` — documents the column contract; the formula pseudocode references `gf_last_10`, `hist_gf_mean`, `hist_gf_std`.
- `tools/verify_duckdb.py` — verifies row counts and FK integrity. Does **not** currently assert specific column names on `dim_team_recent_form`, but should be re-run after the refactor.
- `compound-engineering/proof/CLAUDE.md` memory entry on **"No hardcoded modeling weights"** — same spirit: project-wide consistency is enforced from a single source rather than scattered conventions.

### Institutional Learnings

- The team has already accepted a similar "do it consistently across the repo" approach for tier weights (see `feedback_no_hardcoded_modeling_weights` in MEMORY) and for player identity (see `feedback_player_identity_registry`). A nomenclature standard is the natural extension to read patterns.
- The existing `db/SCHEMA.md` already uses complete words for almost all `dim_*` and `fact_*` columns (`team_code`, `team_name`, `is_wc2026_qualifier`, `gdp_per_capita_usd`, `rank_change`, `snapshot_date`). The drift is concentrated in the read-pattern layer and one CTE inside `dim_team_recent_form`.

### External References

- Not load-bearing for this plan; the repo already has strong internal conventions. No external research conducted.

## Key Technical Decisions

- **Column-name rule: complete words, with four allowed statistical abbreviations.** `avg`, `std`, `mean`, `stats` are allowed. Everything else (`gf`, `ga`, `hist`, `comp`, `pos`, `neg`, `pct`, `pts`, `diff`, `cnt`, `n_*`, `*_n`) is rewritten to its full form. *Rationale:* the four allowed shorts are stable, universally understood statistical terms used in their unambiguous sense; everything else risks ambiguity at read time.
- **Domain acronyms are allowed.** `xg`, `xa`, `fifa`, `gdp`, `iso2`, `iso3`, `usd`, `eur` are kept because they are themselves the canonical names of the underlying concepts. They are *not* abbreviations of English words. *Rationale:* spelling `xg` as `expected_goals` would actively confuse anyone who knows the domain — `xg` is a noun, not an abbreviation.
- **CTE and table names: complete words (with the allowed shorts above).** No `sos`, `hist`, `agg`, `calc`, `tmp`, `t1`/`t2`. `goal_stats` is fine because `stats` is on the allowed list. *Rationale:* CTE names appear in many places (the CTE definition, the FROM clause, any JOIN aliases) and tend to leak into downstream files as conventions — so the rule has to be as tight as the column rule.
- **Join aliases: complete words or no alias.** `JOIN curated.dim_team team USING (team_code)` is fine; `JOIN curated.dim_team t USING (team_code)` is not. Inline `JOIN curated.dim_team USING (team_code)` (no alias) is fine and often clearer. *Rationale:* single-letter aliases are the largest readability cost in the existing queries; they force the reader to scan the FROM/JOIN block to decode every column reference.
- **`goal_diff` → `goal_difference`.** "diff" is an abbreviation. *Rationale:* applies the rule consistently. Touches `curated.fact_international_match`, `staging.team_match`, `curated.dim_team_recent_form`, all queries that read them, and `methodology/curated-poisson-luck/README.md`. (See Risks for the blast-radius treatment.)
- **`n_matches` → `match_count`.** `n_*` and `*_count` both exist in the wild; `match_count` is the canonical form because `count` is a complete word and `n` is the kind of one-letter abbreviation the rule excludes.
- **`w_sum` → `weight_sum`** (or `total_weight` — see open question). The intra-CTE `w` alias (for the per-row `weight`) → `weight`.
- **`sos` CTE → `strength_of_schedule` CTE.** Same rule.
- **`hist_*` column prefix → `historical_*`.** Applied to the four columns in `methodology/curated-poisson-luck/queries/team_model_features.sql` (and consumed in `model.py`).
- **`goal_stats` CTE stays as `goal_stats`.** Confirmed by the user: `stats` is allowed alongside `avg`/`std`/`mean`. The `stats` CTE in `team_goal_stats_for_modeling.sql` is renamed to `goal_stats` (not the other way around) for consistency with the methodology mirror and to give the CTE a self-describing subject.

## Open Questions

### Resolved During Planning

- **Are domain acronyms (`xg`, `xa`, `fifa`, `gdp`, `iso2`, `usd`) covered by the rule?** No — they are the canonical domain names, not English-word abbreviations. The standard explicitly lists them as allowed.
- **Should the standard apply to the raw layer?** No — `raw.*` is a 1:1 mirror of `data/derived/*.parquet` and inherits column names from upstream sources. The rule kicks in at the first transformation (curated, staging).
- **Should `dim_*` / `fact_*` table-name prefixes change?** No — those are the project's existing data-modeling convention, not abbreviations of English words. They stay.
- **`goal_stats` CTE — keep or rename?** Keep. The user confirmed `stats` is on the allowed-shorts list alongside `avg`/`std`/`mean`.

### Deferred to Implementation

- None of the renames depend on runtime-only knowledge.

### Soft — sensible default, will flip on user pushback

- **`w_sum` rename: `weight_sum` or `total_weight`?**
  - Default chosen: `weight_sum` (mechanical translation; `w_sum` was already `(weight)(sum)`).
  - `total_weight` reads slightly better in English but loses the "this is a sum aggregation" signal. Easy to flip if the reviewer prefers it.

## Output Structure

This plan does not create a new directory hierarchy. It adds one new file (`db/NAMING.md`) and edits ~10 existing files.

## Implementation Units

- [ ] **Unit 1: Write the SQL nomenclature standard**

**Goal:** Land `db/NAMING.md` as the canonical convention document for SQL artifacts in this repo. Future PRs (including the remaining units of this plan) reference it.

**Requirements:** R1, R2, R3

**Dependencies:** None (the standard is the input to every other unit).

**Files:**
- Create: `db/NAMING.md`

**Approach:**
- Single-page document, ~80–120 lines.
- Lead with a short "Why this exists" paragraph.
- Six sections:
  1. **Column names** — complete words; allowed shorts (`avg`, `std`, `mean`, `stats`); allowed domain acronyms (`xg`, `xa`, `fifa`, `gdp`, `iso2`, `usd`). With one before/after example each.
  2. **CTE names** — complete words, with the same allowed shorts as columns. Example: `sos` → `strength_of_schedule` (bad → good); `goal_stats` stays as-is (the `stats` short is allowed). The carve-out for `stats` is explicit so future PRs don't relitigate.
  3. **Table aliases** — complete words or no alias. Example: `JOIN curated.dim_team t USING (team_code)` is bad; `JOIN curated.dim_team team USING (team_code)` and `JOIN curated.dim_team USING (team_code)` are both fine.
  4. **What the rule does NOT cover** — raw-layer columns inherited from parquets; master-CSV columns; physical file names; the `dim_`/`fact_`/`staging_` table-name prefixes (these are the project's data-modeling convention, not English abbreviations).
  5. **Examples** — a 10–15 line before/after diff of a real CTE from `db/queries/examples/team_goal_stats_for_modeling.sql`, showing both the column-name and CTE-name renames in one view. Lifted directly from Unit 4's diff.
  6. **Enforcement** — manual review for now. A linter (`tools/lint_sql_names.py`) is deferred and mentioned in a "Future" note.
- Link from `db/SCHEMA.md`'s opening paragraph: "See [`db/NAMING.md`](NAMING.md) for the naming standard applied to all `curated.*` and `staging.*` columns."

**Patterns to follow:**
- Tone and structure of existing `db/SCHEMA.md` — short tables, explicit rules, no preamble.
- Use the existing "Hard rule:" / "Design principle:" framing from `db/SCHEMA.md` where it fits.

**Test scenarios:**
- Test expectation: none -- this unit is documentation only. Verification is by review and by the subsequent units' compliance with the document.

**Verification:**
- `db/NAMING.md` exists, renders in markdown preview, and every example it cites compiles in DuckDB after Units 2–5 land. The document is referenced from `db/SCHEMA.md`.

---

- [ ] **Unit 2: Refactor `db/sql/curated/dim_team_recent_form.sql`**

**Goal:** Rename the view's exposed columns and the internal CTE alias so the view matches the standard. This is the highest-blast-radius file because the view is referenced by name in models.

**Requirements:** R1, R2, R3, R5

**Dependencies:** Unit 1 (standard document is the reference for what to rename to).

**Files:**
- Modify: `db/sql/curated/dim_team_recent_form.sql`

**Approach:**
- Column renames (exposed by the view, so downstream-visible):
  - `gf_last_10` → `goals_for_last_10`
  - `ga_last_10` → `goals_against_last_10`
  - `goal_diff_last_10` → `goal_difference_last_10`
  - `form_points_last_10` → unchanged (already complete words)
  - `gf_last_5` → `goals_for_last_5`
  - `ga_last_5` → `goals_against_last_5`
  - `goal_diff_last_5` → `goal_difference_last_5`
  - `competitive_goal_diff_last_10` → `competitive_goal_difference_last_10`
  - `competitive_form_points_last_10` → unchanged
  - `avg_opponent_fifa_rank_last_10` → unchanged (`avg` is an allowed short; `fifa` is a domain acronym)
- CTE / alias renames (internal, but the standard still applies):
  - CTE `sos` → CTE `strength_of_schedule`
  - JOIN alias `pt` (per_team) → `per_team` (drop the abbreviation; the alias becomes the same as the CTE name, which is fine — the CTE is already named completely)
  - JOIN alias `lm` (last_match) → `last_match`
  - JOIN alias `d` (dim_team) → `team` (or no alias)
- Header comment block: update the column inventory to match. The SoS LIMITATION note stays as-is since `avg_opponent_fifa_rank_last_10` doesn't rename.

**Patterns to follow:**
- The existing `staging.team_match` projection style (lowercase, complete words, no abbreviations) in `db/sql/staging/team_match.sql`.

**Test scenarios:**
- *Integration:* After `tools/build_duckdb.py` runs, `DESCRIBE curated.dim_team_recent_form` returns the renamed columns and no old ones.
- *Integration:* `SELECT goals_for_last_10, goals_against_last_10, goal_difference_last_10 FROM curated.dim_team_recent_form WHERE team_code = 'BRA'` returns a single row with three non-null integers.
- *Integration:* `SELECT gf_last_10 FROM curated.dim_team_recent_form` errors with "column not found" — i.e., the old names are gone, not just shadowed.

**Verification:**
- `python3 tools/build_duckdb.py && python3 tools/verify_duckdb.py` runs clean.
- `grep -rn "gf_last_\|ga_last_\|goal_diff_last_" db/sql/` returns no matches (only the new `goals_for_last_*`/`goals_against_last_*`/`goal_difference_last_*` forms).

---

- [ ] **Unit 3: Refactor `db/sql/staging/team_match.sql` and `db/sql/curated/fact_international_match.sql`**

**Goal:** Apply the `goal_diff` → `goal_difference` rename at its source so Unit 2's renames on `dim_team_recent_form` flow through naturally instead of looking like a one-off translation.

**Requirements:** R1, R5

**Dependencies:** Unit 1.

**Files:**
- Modify: `db/sql/curated/fact_international_match.sql`
- Modify: `db/sql/staging/team_match.sql`

**Approach:**
- In `fact_international_match.sql`: `goal_diff` → `goal_difference`. This column is in the `curated.fact_international_match` table contract documented in `db/SCHEMA.md` line 424.
- In `staging/team_match.sql`: `goal_diff` → `goal_difference`. Documented in `db/SCHEMA.md` line 451.
- Both selections cascade into `dim_team_recent_form` (the source of its `goal_difference_last_*` columns), which is why this unit must land before or with Unit 2 in the build order, not after.

**Patterns to follow:**
- The header-comment style of these two files already conforms — preserve it.

**Test scenarios:**
- *Integration:* `SELECT goal_difference FROM curated.fact_international_match WHERE match_date = '2022-12-18'` returns the expected delta for the WC2022 final.
- *Integration:* `SELECT goal_difference FROM staging.team_match WHERE team_code = 'ARG' AND match_date = '2022-12-18' AND venue = 'N'` returns the same value (positive for Argentina).
- *Integration:* `SELECT goal_diff FROM curated.fact_international_match LIMIT 1` errors.

**Verification:**
- `python3 tools/build_duckdb.py && python3 tools/verify_duckdb.py` passes.
- `grep -rn "goal_diff\b" db/sql/` returns no matches.

---

- [ ] **Unit 4: Refactor `db/queries/examples/` SQL files**

**Goal:** Bring every example query into compliance. These are the patterns model authors are encouraged to copy from, so they have to be exemplary.

**Requirements:** R1, R2, R3

**Dependencies:** Units 2 and 3 (the example queries SELECT from the renamed view/fact columns).

**Files:**
- Modify: `db/queries/examples/team_goal_stats_for_modeling.sql`
- Modify: `db/queries/examples/curated_poisson_luck_per_team_features.sql`
- Modify: `db/queries/examples/team_recent_results.sql`
- Modify: `db/queries/examples/attack_vs_defense_per_team.sql`

**Approach:**

For `team_goal_stats_for_modeling.sql` and `curated_poisson_luck_per_team_features.sql` (they share the same CTE skeleton):

Column renames inside the CTEs and final SELECT:
- `gf` → `goals_for`
- `ga` → `goals_against`
- `gf_mean` → `goals_for_mean`
- `gf_std` → `goals_for_std`
- `ga_mean` → `goals_against_mean`
- `ga_std` → `goals_against_std`
- `n_matches` → `match_count`
- `w_sum` → `weight_sum` (or `total_weight` per OQ2)
- inline `w` alias for `weight` → `weight` (drop the `AS w` rename; `weight` is already the underlying column name)

CTE renames:
- `team_match` — unchanged (already complete)
- `weighted` — unchanged (complete word, but consider `weighted_team_match` for self-description; assumed default: keep `weighted`)
- `means` — unchanged (complete word)
- `stats` → `goal_stats` (in `team_goal_stats_for_modeling.sql`) — give the CTE a self-describing subject and match the methodology mirror
- `goal_stats` — unchanged (in `curated_poisson_luck_per_team_features.sql`); `stats` is on the allowed-shorts list

JOIN alias renames in these two files:
- `tm` → `team_match`
- `tw` → `tier_weight`
- `w` (weighted CTE) → `weighted`
- `m` (means CTE) → `means`
- `s` (stats CTE) → `goal_stats`
- `t` (dim_team) → `team`
- `c` (dim_team_current) → `team_current`
- `f` (dim_team_recent_form) → `recent_form`
- `g` (goal_stats CTE) → `goal_stats`

For `curated_poisson_luck_per_team_features.sql`, the final SELECT also produces the `hist_*` columns:
- `hist_n_matches` → `historical_match_count`
- `hist_gf_mean` → `historical_goals_for_mean`
- `hist_gf_std` → `historical_goals_for_std`
- `hist_ga_mean` → `historical_goals_against_mean`
- `hist_ga_std` → `historical_goals_against_std`

For `team_recent_results.sql`:
- `gf` / `ga` inline aliases → `goals_for` / `goals_against`
- `tv` alias for `team_view` CTE → `team_view`

For `attack_vs_defense_per_team.sql`:
- `a` (attack CTE) → `attack`
- `d` (defense CTE) → `defense`
- `t` (dim_team) → `team`
- All exposed column names already comply; no renames needed.

**Patterns to follow:**
- The verbose-but-readable style of `db/sql/curated/dim_team_recent_form.sql` after Unit 2 lands.

**Test scenarios:**
- *Integration:* Each example query runs against the rebuilt `data/wc2026.duckdb` and returns a result set with the same row count as before the refactor.
  - `team_goal_stats_for_modeling.sql`: same 48 rows, same `goals_for_mean` ordering as before.
  - `curated_poisson_luck_per_team_features.sql`: same 48 rows, `historical_goals_for_mean` column present, `historical_goals_for_std` non-null for every WC2026 qualifier with ≥ 5 matches since 2022.
  - `team_recent_results.sql`: returns the same rows.
  - `attack_vs_defense_per_team.sql`: returns the same rows.
- *Integration:* `grep -E "AS (gf|ga|gf_mean|gf_std|ga_mean|ga_std|n_matches|w_sum|hist_)" db/queries/examples/` returns no matches.

**Verification:**
- All four queries run cleanly via `duckdb data/wc2026.duckdb < <file>`.
- `grep -rEn "^[[:space:]]*[a-z] AS " db/queries/examples/` returns no matches (no single-letter aliases anywhere in the directory).

---

- [ ] **Unit 5: Refactor `methodology/curated-poisson-luck/queries/` + update `model.py`**

**Goal:** Bring the canonical-home queries for the curated-poisson-luck model into compliance, and update the Python model to read the renamed columns.

**Requirements:** R1, R2, R3, R5

**Dependencies:** Unit 4 (these are the "canonical home" files that the `db/queries/examples/` files mirror; they share the same skeleton and same renames).

**Files:**
- Modify: `methodology/curated-poisson-luck/queries/team_goal_stats.sql`
- Modify: `methodology/curated-poisson-luck/queries/team_model_features.sql`
- Modify: `methodology/curated-poisson-luck/model.py`

**Approach:**
- Apply the exact same column-name and alias renames from Unit 4 to the two methodology SQL files. They are byte-for-byte mirrors of the example queries (per their own comments), so the diffs are identical. The `goal_stats` CTE name stays.
- Additional renames in `team_goal_stats.sql`:
  - Exposed columns are `gf_weighted_mean`, `gf_weighted_std`, `ga_weighted_mean`, `ga_weighted_std`. Rename to `goals_for_weighted_mean`, `goals_for_weighted_std`, `goals_against_weighted_mean`, `goals_against_weighted_std`.
- In `model.py`:
  - The model reads `features["hist_gf_mean"]` at the line documented in research (`methodology/curated-poisson-luck/model.py:77`). Update to `features["historical_goals_for_mean"]`.
  - Grep for any other column references and update them in the same diff.
- Confirm `model.py`'s public interface (function signatures, return values) is unchanged — only the internal column-name reads shift.

**Patterns to follow:**
- Match the exact column ordering used in the corresponding `db/queries/examples/` file so the mirror relationship documented in the file headers stays accurate.

**Test scenarios:**
- *Happy path:* `python3 -c "from methodology.curated_poisson_luck.model import build_features; print(build_features().columns.tolist())"` (or equivalent module entrypoint) emits a column list containing `historical_goals_for_mean`, `historical_goals_for_std`, `historical_goals_against_mean`, `historical_goals_against_std` and no `hist_*` entries.
- *Happy path:* `python3 methodology/curated-poisson-luck/model.py` (or the project's standard model run command) produces a `predictions.csv` with the same row count and same first-decimal-place probabilities as the pre-refactor run for one fixed match (capture a baseline value before Unit 5, compare after).
- *Error path:* Searching `methodology/curated-poisson-luck/model.py` for the string `hist_gf` returns no matches.

**Verification:**
- The model run produces predictions, the prediction count matches the pre-refactor baseline (this is a pure rename — no math changes), and the comparison framework downstream still ingests the predictions.
- `grep -rEn "hist_gf|hist_ga|gf_mean|gf_std|ga_mean|ga_std" methodology/` returns no matches.

---

- [ ] **Unit 6: Refresh `db/SCHEMA.md` and `methodology/curated-poisson-luck/README.md`**

**Goal:** Documentation matches the renamed columns. No future reader sees the old names anywhere in the repo.

**Requirements:** R5

**Dependencies:** Units 2, 3, 4, 5 (the source-of-truth files those units edit).

**Files:**
- Modify: `db/SCHEMA.md`
- Modify: `methodology/curated-poisson-luck/README.md`

**Approach:**
- In `db/SCHEMA.md`:
  - `goal_diff` → `goal_difference` in the `fact_international_match` table (line ~424).
  - Same rename in the `staging.team_match` table (line ~451).
  - The `dim_team_recent_form` column inventory (lines ~470–487) gets the full `gf_last_*` → `goals_for_last_*`, `ga_last_*` → `goals_against_last_*`, `goal_diff_last_*` → `goal_difference_last_*`, `competitive_goal_diff_last_10` → `competitive_goal_difference_last_10` rename.
  - Add a sentence at the top of the file (right after the existing "Design principle" line) pointing to `db/NAMING.md`.
- In `methodology/curated-poisson-luck/README.md`:
  - Pseudocode-formula renames: `gf_last_10` → `goals_for_last_10`, `hist_gf_mean` → `historical_goals_for_mean`, `hist_gf_std` → `historical_goals_for_std`. ~5 line-edits in total.
  - The "What this model reads" table (line ~21) — update `gf_mean`/`gf_std`/`ga_mean`/`ga_std` references to the new column names.

**Patterns to follow:**
- Existing formatting in both docs — short tables, fenced code blocks, no preamble.

**Test scenarios:**
- Test expectation: none -- documentation-only. Verification is by review.

**Verification:**
- `grep -rEn "gf_|ga_|hist_gf|hist_ga|goal_diff\b|n_matches|w_sum\b" db/ methodology/` returns zero matches across SQL, markdown, and Python files.
- The cross-link from `db/SCHEMA.md` to `db/NAMING.md` resolves on GitHub's renderer.

---

- [ ] **Unit 7: Re-run verify and capture before/after diff for the PR description**

**Goal:** Prove the refactor is correctness-preserving and end the plan with a clean repo.

**Requirements:** R7

**Dependencies:** Units 2–6.

**Files:**
- (No file changes — this is a verification + PR-description-prep step.)

**Approach:**
- Run `python3 tools/build_duckdb.py` cold (delete the existing `data/wc2026.duckdb` first to force a full rebuild).
- Run `python3 tools/verify_duckdb.py`.
- For the curated-poisson-luck model: capture a sample-row baseline from `predictions.csv` for one fixed match (e.g., BRA vs ARG) before any Unit 5 edits land, and again after Unit 5 lands. The probabilities should match to at least 3 decimal places — this is a pure rename, not a math change.
- Run the four example queries and the two methodology queries; eyeball that row counts and the first 5 rows match the pre-refactor results.
- Repo-wide grep one more time:
  - `grep -rEn "\bgf\b|\bga\b|\bgf_(mean|std|last_5|last_10)\b|\bga_(mean|std|last_5|last_10)\b|\bn_matches\b|\bw_sum\b|\bhist_gf\b|\bhist_ga\b|\bsos\b|\bgoal_diff\b" db/ methodology/ tools/ 2>&1 | grep -v "^\\s*--"` should be empty.

**Test scenarios:**
- *Happy path:* `verify_duckdb.py` exits 0.
- *Happy path:* All four example queries return the same row count as a pre-refactor capture.
- *Happy path:* The curated-poisson-luck `predictions.csv` matches the pre-refactor capture row-for-row at 3 decimal places for a fixed match.

**Verification:**
- All three checks above pass before opening the PR. Capture a one-line "before/after row count" table for the PR description.

## System-Wide Impact

- **Interaction graph.** The renamed columns on `curated.dim_team_recent_form` propagate to: `methodology/curated-poisson-luck/queries/team_model_features.sql`, `methodology/curated-poisson-luck/model.py`, and every `db/queries/examples/*.sql` file that joins the view. All of these are touched in this plan. There is one consumer outside this loop: `tools/verify_duckdb.py` — verified by Unit 7 to still pass.
- **Error propagation.** The DuckDB build is `CREATE OR REPLACE`, so a stale-column reference will fail loudly at build time (DuckDB's column-not-found error). Same for Python — `KeyError` on `features["hist_gf_mean"]` will be obvious. There is no silent-failure path: any miss in the rename surfaces at the next `build_duckdb.py` or `model.py` invocation.
- **State lifecycle risks.** None. The masters under `db/masters/` are unchanged; the curated tables are rebuilt fresh on every run; no migration of persistent data is required.
- **API surface parity.** The plan touches both the canonical-home methodology queries and their `db/queries/examples/` mirrors in the same PR — the convention that "examples mirror canonical home" is preserved.
- **Integration coverage.** Captured in Unit 7's before/after baseline against the curated-poisson-luck `predictions.csv`. A pure rename should produce identical predictions; any divergence is the signal to halt and inspect.
- **Unchanged invariants.** Master CSVs, raw layer column names, table names (`dim_*` / `fact_*` / `staging.*`), file names, and the `tools/build_duckdb.py` / `tools/verify_duckdb.py` interfaces are all explicitly out of scope.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| **Hidden consumer not on the grep paths.** A notebook, scratch script, or untracked file references `gf_last_10` or `hist_gf_mean` and silently breaks the next time it runs. | Unit 7 runs a repo-wide grep across all source dirs (`db/`, `methodology/`, `tools/`, plus the project root for any committed notebooks). Untracked scratch files are accepted collateral — the cost of one developer fixing their local scratch is far smaller than the cost of leaving the standard half-applied. |
| **Predictions drift.** Renaming `hist_gf_mean` to `historical_goals_for_mean` in `model.py` but missing a usage point inside the model produces a `KeyError` or — worse — pulls the wrong column and silently produces wrong predictions. | Unit 7's pre-refactor baseline capture and exact-comparison against the post-refactor `predictions.csv` (to 3 decimal places, fixed match) is the load-bearing check. If the baseline doesn't match, halt and inspect. |
| **Reviewer pushback on `goal_difference` (verbose).** Reviewer might argue `goal_diff` is universally understood and the rename is gratuitous churn. | The standard explicitly allows `avg`, `std`, `mean`, `stats` and no other English-word abbreviations; `diff` is excluded by the rule. The PR description should lead with the rule, not the rename. If the reviewer wants to add `diff` to the allowlist, that's a one-line edit to `db/NAMING.md` in a follow-up. |
| **Two PRs touch the same files concurrently.** Another in-flight branch edits `dim_team_recent_form.sql` or the curated-poisson-luck queries. | The git status at the start of this plan shows `db/sql/curated/dim_team_recent_form.sql` is in untracked / modified state already. Confirm there is no in-flight PR touching the same files before starting Unit 2. If there is, sequence after it lands. |

## Documentation / Operational Notes

- The new `db/NAMING.md` is the load-bearing artifact long-term. Cross-link from `AGENTS.md` / `CLAUDE.md` so future agents pick it up at session start (one-line addition under the "Cross-cutting" bullet list in both files — optional but recommended).
- A future `tools/lint_sql_names.py` is the natural follow-up: a small Python script that greps for the disallowed patterns and exits non-zero. Out of scope for this PR; tracked as a deferred item.
- No rollout, monitoring, or migration concerns — this is a pure refactor of code and docs.

## Sources & References

- **Origin:** This plan was created directly from a `/ce-plan` invocation, not from a brainstorm document. The naming rule was specified inline in the invocation.
- **Code referenced:**
  - `db/SCHEMA.md`
  - `db/sql/curated/dim_team_recent_form.sql`
  - `db/sql/curated/fact_international_match.sql`
  - `db/sql/staging/team_match.sql`
  - `db/queries/examples/team_goal_stats_for_modeling.sql`
  - `db/queries/examples/curated_poisson_luck_per_team_features.sql`
  - `db/queries/examples/team_recent_results.sql`
  - `db/queries/examples/attack_vs_defense_per_team.sql`
  - `methodology/curated-poisson-luck/queries/team_goal_stats.sql`
  - `methodology/curated-poisson-luck/queries/team_model_features.sql`
  - `methodology/curated-poisson-luck/model.py`
  - `methodology/curated-poisson-luck/README.md`
  - `tools/verify_duckdb.py`
- **Memory entries consulted:**
  - `feedback_no_hardcoded_modeling_weights` — same single-source-of-truth spirit, applied here to naming.
  - `reference_curated_schema` — confirms `db/SCHEMA.md` is the canonical column inventory to keep in sync.
