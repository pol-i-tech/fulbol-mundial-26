---
title: "fix: Data cleanse for games, teams, and players"
type: fix
status: active
date: 2026-05-06
---

# fix: Data cleanse for games, teams, and players

## Overview

The model pipeline blends StatsBomb national-team data, Understat club-season data, and a Wikipedia-scraped WC2026 squad list into `data/derived/squad_xg_ratings.parquet`, `team_attack_ratings.parquet`, `statsbomb_player_xg.parquet`, and `statsbomb_team_xg.parquet`. A first-pass scan shows real data-quality bias entering the model — most importantly small-sample per-90 inflation that produces players with `blended_xg90` up to 7.99 — plus structural issues (Understat join leaks, non-qualifier nations, multi-club join artifacts, name encoding drift). This plan introduces a deterministic audit script, a reviewable manual-override layer, and targeted fixes in the build pipeline so the data feeding statistical models is clean and reproducible.

This is a data-quality fix plan, not a model change plan. Model coefficients (the 0.4/0.6 blend, Dixon-Coles `xi`, etc.) are out of scope.

## Problem Frame

Statistical models in this repo (`compound-model`, `ensemble_model.py`, `wc2022_xg_backtest.py`) read directly from `data/derived/`. Five concrete issues bias those models today:

1. **Small-N per-90 inflation.** `tools/build_squad_xg_ratings.py` blends `nat_xg_per_90` even when `nat_minutes` is tiny. Pablo Sarabia ends up at `blended_xg90 = 7.99` from 4 national-team minutes (1 chance → 22 xg/90). 350 of 1275 squad rows have `nat_minutes < 90`; 607 have `nat_minutes < 180`.
2. **Understat join leaks "multi-club" strings.** 22 rows have `club = "Fiorentina,Monza"` style values because the Understat aggregation collapses a player's two clubs in a season into a single string field. This breaks any downstream code that assumes `club` is a single entity and silently inflates `club_minutes_2425`.
3. **Squad scope mismatch.** `nation` has 52 distinct values but WC2026 has 48 finals teams. Albania, Bolivia, Czech Republic, Georgia, Hungary, Peru, Qatar, Romania, Slovakia, Slovenia, Turkey, Ukraine, Venezuela, Wales, Scotland are present (some are non-qualifiers). The pipeline does not declare which list is canonical.
4. **Understat nationality column is unusable.** All 6808 Understat rows have empty `nationality`. Code that joins on it will silently fail. The squad join uses fuzzy-name matching, but downstream features that *think* they are nationality-aware are not.
5. **Cross-source naming drift.** `M''Baye Babacar Niang` (double apostrophe), full Iberian-style names ("Cristiano Ronaldo dos Santos Aveiro") vs short form, accent normalization done only in `simplify_name()` of the build script — names returned to consumers (CSV/parquet) are *not* normalized, so cross-source joins outside the build script can miss.

Players on the wrong nationality (the user's specific concern) is a sub-case of (3) and (4) — without a verified canonical squad list, we cannot detect it. Once a canonical list exists, suspicious entries get patched via overrides with cited sources.

## Requirements Trace

- R1. Produce a deterministic, re-runnable audit report that lists every data-quality issue across `squad_xg_ratings`, `team_attack_ratings`, `sb_player_summary`, `statsbomb_player_xg`, `statsbomb_team_xg`, and `understat_player_xg`.
- R2. Eliminate small-sample per-90 inflation (no `blended_xg90` driven primarily by `< ~3 full matches` of national-team play).
- R3. Resolve multi-club join artifacts (one canonical club per player-season, or an explicit list — never a comma-joined string).
- R4. Establish the canonical WC2026 nation list (48 teams) and label any non-qualifier rows so downstream code can filter explicitly.
- R5. Verify suspicious player–team and player–nationality assignments against authoritative sources (FIFA squad announcements, Wikipedia, transfermarkt) and patch via a citable override layer; when uncertain, still apply best-known correction.
- R6. After the cleanse, re-run `tools/build_squad_xg_ratings.py` and confirm zero rows breach the audit thresholds.
- R7. The cleanse must be reproducible from `data/raw/` — no manually edited derived parquet files.

## Scope Boundaries

- Not changing the `0.4 × nat + 0.6 × club` blend formula or any model hyperparameters.
- Not pulling new data sources (no Transfermarkt or FBref scrapers added — FBref is hard-blocked anyway per `DEVELOPMENT.md`).
- Not changing the Kalshi/Polymarket market normalization paths.
- Not auditing `kalshi_snapshot_*` or `polymarket_snapshot_*` market data — separate concern.
- Not auditing `data/raw/elo/` or the Elo-baseline model inputs — those are read directly by `tools/weekly_pull.py` from `martj42` and need a separate look if the user wants.
- Online lookups for player corrections are bounded: a sampled-but-thorough sweep of every flagged row, not a top-down scrape of every WC2026 player.

### Deferred to Separate Tasks

- Adding new data sources (UCL, Nations League event data) — Track B contribution.
- Re-fitting Dixon-Coles after cleansed inputs — natural next step but separate plan.
- Building a long-running automated data-validation CI gate — start with a script, productionize later.

## Context & Research

### Relevant Code and Patterns

- `tools/build_squad_xg_ratings.py` — fuzzy-matches StatsBomb names against Understat via `rapidfuzz` (threshold 75); applies `simplify_name()` only inside the build, not in the output. This is where the small-N inflation lives — `blended_xg90 = 0.4*nat + 0.6*club` runs unconditionally.
- `tools/aggregate_statsbomb_players.py` — produces `sb_player_summary.parquet` with `xg_per_90 = xg / minutes_played * 90`; minute floor not enforced.
- `tools/pull_understat_players.py` — produces `understat_player_xg_raw.parquet` and the derived aggregate; the multi-team string concatenation happens on the season aggregation step. Note that `tools/build_squad_xg_ratings.py` filters Understat to `time >= 200` minutes before joining, so club-side per-90 has a 200-minute minimum at the point of blending.
- `tools/pull_wc2026_squads.py` — Wikipedia-scraped, 52-team output. Source of the squad scope mismatch.
- `tools/pull_statsbomb.py` — pulls `FIFA WC 2018/2022`, `Euro 2020/2024`, `Copa America 2024` — only competitions present today; team names mostly clean but `M''Baye` shows minor encoding noise.
- `tools/weekly_pull.py` — holds `NAME_TO_FIFA3` and `ISO2_TO_FIFA3` dicts. These are the only existing canonical nation/code mappings; reuse them rather than duplicating.

### Institutional Learnings

- `docs/solutions/raw/` is empty; no prior cleanse documented. This plan also produces the first solution writeup.
- `DEVELOPMENT.md` "Subjectivity and bias policy" — every manual adjustment must be documented with evidence and reasoning. Override CSV rows must follow this convention (one row = one decision + cited source).

### Concrete Issues Found in First-Pass Scan

| Issue | Surface area | Example | Severity |
|---|---|---|---|
| Small-N nat per-90 inflation | `squad_xg_ratings.blended_xg90` | Pablo Sarabia: 4 nat min → 7.99 blended | High — directly biases attack ratings |
| Multi-club Understat join | `squad_xg_ratings.club` | "Fiorentina,Monza"; 22 rows | Medium — silent in current code, breaks any new join |
| Squad nation scope | `squad_xg_ratings.nation` | 52 nations vs 48 WC26 teams | High — non-qualifier rows pollute team-level aggregates |
| Empty Understat nationality | `understat_player_xg.nationality` | All 6808 rows blank | Medium — lurking footgun |
| Name encoding drift | `statsbomb_player_xg.player` | `M''Baye Babacar Niang` | Low — but compounds with cross-source joins |
| Sb teams not in squad | `statsbomb_team_xg.team` | Egypt, Finland, Iceland, Nigeria, North Macedonia, Russia, Sweden | Low — historical; only matters if any are wrongly excluded from squad list |
| High Understat-miss rate per nation | `squad_xg_ratings` (54% rows missing club) | Qatar 95%, Iran 90%, Australia 85% | High — those nations effectively ride on nat-only stats and inherit (1) |
| Single-shot StatsBomb xG | `statsbomb_player_xg.xg` | Max 0.99 — within bounds | None observed; verified clean |
| Team-match StatsBomb xG | `statsbomb_team_xg.xg` | Max 6.93 (Spain–Switzerland 2021 R16) | None observed; matches reality |

### External References

External research is not needed for the structural cleanse. Specific player corrections will cite:

- Wikipedia squad pages (`https://en.wikipedia.org/wiki/<Team>_at_the_2026_FIFA_World_Cup`) — used by `pull_wc2026_squads.py` already
- FIFA's official squad announcement when available
- Transfermarkt (`https://www.transfermarkt.com/<player-slug>`) for current club + nationality
- The squad page on each national federation's site as a tiebreaker

These are accessed manually during the lookup step; no automated scraper is built.

## Key Technical Decisions

- **Audit-first, override-second pattern.** A single `tools/audit_data_quality.py` script produces a deterministic report (`results/audits/<date>/data_quality.md` + machine-readable `issues.csv`). Fixes land as either pipeline changes (for systemic issues like small-N inflation) or rows in `data/manual_overrides/player_corrections.csv` (for individual records). Rationale: separates detection from correction so the audit can re-run after fixes and confirm zero residual issues; mirrors `DEVELOPMENT.md`'s reproducibility-and-evidence policy.

- **Minimum-minutes rule with shrinkage, not a hard cutoff.** For `nat_xg_per_90` we apply Bayesian-style shrinkage: `effective_xg90 = (xg + prior_mean × prior_minutes) / (minutes + prior_minutes) × 90`, where `prior_mean` is the position-weighted xG/90 from `sb_player_summary` and `prior_minutes` is set so anything below ~3 full matches (270 min) is pulled most of the way back to prior. Rationale: dropping rows entirely loses signal for legitimate squad members; raw per-90 from 4 minutes is meaningless. Shrinkage is the standard fix; we apply it inside the existing build script and document the prior in `methodology/`.

- **Multi-club rows: collapse to weighted average, retain raw list.** Replace the `club` string with a single canonical value (the club where the player has the most minutes for the season) and store the multi-club detail in a new column `club_history` (list type) for transparency. Rationale: downstream code expects scalar `club`; we don't break consumers.

- **Canonical 48-team list lives in `tools/wc2026_qualifiers.py`** as a Python constant referenced from both `pull_wc2026_squads.py` and the audit script. Adds an `is_wc2026_qualifier` boolean to `squad_xg_ratings` and `team_attack_ratings`. Rationale: explicit > implicit; no row deletion (preserves auditability); downstream code chooses to filter or not. Source for the list: FIFA's confirmed-qualifiers page as of plan date (cited in the constants file).

- **Manual overrides use a CSV with mandatory `source_url` and `reason` columns.** Schema: `entity_type,entity_id,field,old_value,new_value,source_url,reason,reviewed_by,reviewed_date`. Applied in a single function called late in `build_squad_xg_ratings.py` (and other build scripts as needed). Rationale: every correction is auditable and complies with the subjectivity-and-bias policy in `DEVELOPMENT.md`.

- **Apply normalization once, in the pull layer, not in every consumer.** `simplify_name()` currently lives only inside `build_squad_xg_ratings.py`. Move it to a shared `tools/_names.py` and apply during pull → derived transforms so the parquet output already has a `player_normalized` column. Original name preserved as `player`. Rationale: cleaner outputs, fewer surprises for new contributors.

## Open Questions

### Resolved During Planning

- **Should we drop non-qualifier nations entirely?** No. Mark them with `is_wc2026_qualifier=False` and let consumers filter. Rationale: the squad scrape may have run before final qualification; preserving rows keeps history. (Carried through to Unit 4.)
- **Where do per-player corrections live?** A reviewed CSV under `data/manual_overrides/`, applied at build time. Rationale: matches the existing data flow and is git-trackable.
- **Do StatsBomb shot-level xG values have any outlier issues?** No — observed max is 0.99, count 6619, distribution sane. Skip. (Audit script still includes the check so we catch future regressions.)
- **What audit threshold for "outlier blended_xg90"?** Position-aware: forward `> 1.4`, midfielder `> 0.9`, defender `> 0.6`, GK `> 0.05`. Each is roughly the 99th percentile of historical national-team xG/90 in `sb_player_summary` after applying the minutes floor. Documented in the audit script.

### Deferred to Implementation

- Exact prior-minutes constant for shrinkage — start at 270 (3 matches) but tune by checking that no flagged outlier survives while no defensible scorer (e.g., Lautaro Martínez at high but credible rates) gets crushed. Final value lives in `methodology/_data-cleanse/README.md`.
- Whether to apply shrinkage to `club_xg_per_90` as well — Understat already enforces a 200-minute floor at the source, but post-shrinkage check may show residual inflation. Decide during Unit 2 with data in hand.
- Final list of player corrections and how many — knowable only after the audit script first runs. Plan budgets a sweep through every row flagged High/Medium severity.

## Implementation Units

- [ ] **Unit 1: Audit script — single source of truth for data-quality issues**

**Goal:** Build `tools/audit_data_quality.py` that scans every derived parquet and produces a deterministic Markdown report plus a machine-readable `issues.csv`. The report is the input to all downstream cleanse work and the exit criterion for verifying it succeeded.

**Requirements:** R1, R6.

**Dependencies:** None.

**Files:**
- Create: `tools/audit_data_quality.py`
- Create: `tools/_names.py` (extracted from `build_squad_xg_ratings.py`; shared by audit and build)
- Create: `results/audits/_template/data_quality.md`
- Test: `tools/test_audit_data_quality.py`

**Approach:**
- One check class per issue category from the table above; each emits 0..N rows of a common `Issue(entity_type, entity_id, severity, category, detail, suggestion)` dataclass.
- Categories: `outlier_blended_xg90`, `outlier_nat_xg90`, `outlier_understat_xg90`, `multi_club_artifact`, `non_qualifier_nation`, `empty_understat_nationality`, `name_encoding_drift`, `name_unmatched_across_sources`, `team_xg_outlier`, `single_shot_xg_outlier`, `nation_with_high_understat_miss_rate`.
- Outputs:
  - `results/audits/<YYYY-MM-DD>/data_quality.md` — human-readable summary by category
  - `results/audits/<YYYY-MM-DD>/issues.csv` — flat CSV used as input to Unit 5 corrections
- Idempotent and deterministic: no random sampling; no network calls.
- Position-aware xG thresholds documented inline (see `Resolved During Planning`).

**Patterns to follow:**
- Mirror the simple "load parquet → assert on dataframe → write CSV" style of `tools/aggregate_statsbomb_players.py`. No class hierarchy, no plugin registration — KISS.
- Follow the `as_of_date` folder convention used by `results/<model>/<date>/`.

**Test scenarios:**
- Happy path — Run on current `data/derived/` and assert the issues.csv contains the Pablo Sarabia outlier and at least 22 multi-club rows.
- Happy path — Re-running on the same input produces a byte-identical CSV (deterministic).
- Edge case — Run on a synthetic minimal fixture with one row of each category; assert each category produces exactly one issue.
- Edge case — Empty dataframe input produces an empty issues.csv with header row, not a crash.
- Integration — Sum of rows in issues.csv equals sum of rows the Markdown report claims per category.

**Verification:**
- First run produces a non-empty `issues.csv` containing all known issues from the first-pass scan.
- Re-running after Units 2–5 land produces an `issues.csv` whose only High-severity rows are explicitly accepted with documented reasoning.

---

- [ ] **Unit 2: Small-N shrinkage in the squad-rating build**

**Goal:** Eliminate per-90 inflation in `squad_xg_ratings.blended_xg90` driven by tiny `nat_minutes` samples.

**Requirements:** R2.

**Dependencies:** Unit 1 (so we can verify the fix shrinks the count of flagged outliers to zero).

**Files:**
- Modify: `tools/build_squad_xg_ratings.py`
- Create: `methodology/_data-cleanse/README.md` (documents the shrinkage prior and the position-weighted base rates)
- Test: `tools/test_build_squad_xg_ratings.py`

**Approach:**
- Compute `prior_mean_xg90` per position from `sb_player_summary` after filtering to `minutes_played >= 270`.
- Replace raw `nat_xg_per_90` in the blend with `shrunk_nat_xg_per_90 = (player_xg + prior_mean × prior_minutes) / (player_minutes + prior_minutes) × 90`. Default `prior_minutes = 270`.
- Recompute `blended_xg90` from the shrunk value.
- Persist both columns: keep `nat_xg_per_90` (raw) for transparency; add `nat_xg_per_90_shrunk` and recompute `blended_xg90` from the shrunk one.
- Add a unit-level constant block with the prior values, sourced from `sb_player_summary`, regenerated each run (no hard-coded magic numbers).

**Patterns to follow:**
- Same parquet-write idiom already in `build_squad_xg_ratings.py`.
- Use `np.where` rather than row iteration for the shrinkage step.

**Technical design:** *(directional, not implementation)*

```
For each squad row:
  pos = position_bucket(player.position)            # F | M | D | GK
  prior = position_priors[pos]                       # mean nat-xg/90 for that bucket, ≥270min cohort
  shrunk = (player.nat_xg + prior × 270) /
           (player.nat_minutes + 270) × 90
  blended = 0.4 × shrunk + 0.6 × club_xg_per_90      # if club known
          = shrunk                                    # else
```

**Test scenarios:**
- Happy path — A player with 270 min and 1.0 nat xg/90 stays close to 1.0 (drift < 0.2).
- Edge case — A player with 4 min and one big chance lands within ±0.2 of the position prior.
- Edge case — A player with 0 nat minutes returns the position prior, not NaN, not div-by-zero.
- Edge case — Position is empty/unknown — falls back to the global mean prior, not NaN.
- Integration — After this unit, the audit (Unit 1) reports zero `outlier_blended_xg90` issues except those explicitly whitelisted with cited justification.

**Verification:**
- Pablo Sarabia row drops from `blended_xg90 = 7.99` to a credible value (< 1.0 expected).
- The 350 rows with `nat_minutes < 90` no longer appear in the top-50 `blended_xg90`.
- `data/derived/squad_xg_ratings.parquet` has both raw and shrunk columns.

---

- [ ] **Unit 3: Multi-club Understat join — collapse to canonical club**

**Goal:** Replace the comma-concatenated `club` artifact with a single canonical club + a transparent `club_history` list, so downstream code can rely on `club` being a single entity.

**Requirements:** R3.

**Dependencies:** None (independent of Unit 2; can land in either order).

**Files:**
- Modify: `tools/pull_understat_players.py` (or `tools/build_squad_xg_ratings.py` if the artifact originates in the squad join — Unit will confirm first)
- Test: `tools/test_understat_join.py`

**Approach:**
- Locate where the comma-join happens. Two candidates:
  1. `pull_understat_players.py` — when aggregating across multiple Understat club-seasons for one player.
  2. `build_squad_xg_ratings.py` — when fuzzy-matching produces multiple Understat candidates for one StatsBomb player.
- Replace the string concat with a structured list and an explicit reduction:
  - `club` = club with most minutes in the most recent season the player appeared in
  - `club_history` = list of `(club, league, minutes, xg_per_90, season)` tuples
  - `club_minutes_2425` = sum (current behavior preserved)
  - `club_xg_per_90` = minutes-weighted average (current effective behavior, made explicit)

**Patterns to follow:**
- The `sb_player_summary` aggregation in `aggregate_statsbomb_players.py` already does minutes-weighted aggregation — mirror that style.

**Test scenarios:**
- Happy path — A single-club player produces `club_history` of length 1 and `club` matching that club.
- Edge case — A player with two clubs (e.g., Stefan Posch Atalanta+Bologna) produces `club_history` length 2, `club = "Bologna"` (the higher-minutes one), no comma in the string.
- Edge case — A player whose two clubs have equal minutes deterministically picks one (alphabetical tiebreak; documented).
- Integration — After this unit, the audit (Unit 1) reports zero `multi_club_artifact` issues.

**Verification:**
- Zero rows in `squad_xg_ratings` contain a comma in the `club` field.
- `club_history` column exists and is populated for all 22 originally affected rows.

---

- [ ] **Unit 4: WC2026 qualifier scope — explicit canonical list**

**Goal:** Declare the 48-team WC2026 finals list as code, label every squad row with `is_wc2026_qualifier`, and make non-qualifier rows easy to filter.

**Requirements:** R4.

**Dependencies:** None.

**Files:**
- Create: `tools/wc2026_qualifiers.py` — single Python constant `WC2026_QUALIFIERS: frozenset[str]` plus `SOURCE_URL` and `LAST_UPDATED` metadata
- Modify: `tools/pull_wc2026_squads.py` — annotate output with the boolean
- Modify: `tools/build_squad_xg_ratings.py` — propagate the boolean
- Modify: `tools/audit_data_quality.py` — flag rows where `is_wc2026_qualifier=False`
- Test: `tools/test_wc2026_qualifiers.py`

**Approach:**
- Hard-code the list as of plan date with `SOURCE_URL` (FIFA confirmed-qualifiers page) and `LAST_UPDATED = '2026-05-06'`.
- Validate at module import: 48 unique entries, all match canonical strings used elsewhere (cross-checked against `NAME_TO_FIFA3` keys in `weekly_pull.py`).
- Audit reports any squad nation outside the set as a `non_qualifier_nation` issue (Severity: Info, not Error — the row is preserved).

**Patterns to follow:**
- Match the existing `NAME_TO_FIFA3` dict format in `tools/weekly_pull.py` (3-letter codes, full canonical names).

**Test scenarios:**
- Happy path — 48 entries, no duplicates, all map cleanly to FIFA3 codes.
- Edge case — Module import fails loudly if the cross-check vs `NAME_TO_FIFA3` finds a typo.
- Integration — After this unit lands, `squad_xg_ratings` includes `is_wc2026_qualifier`, and the audit shows the expected 4 non-qualifier nations as Info.

**Verification:**
- `data/derived/squad_xg_ratings.parquet` has `is_wc2026_qualifier` populated.
- Filtering to `is_wc2026_qualifier=True` yields exactly 48 distinct nations.

---

- [ ] **Unit 5: Manual overrides layer**

**Goal:** Add the override CSV plus the apply-step in the build, so individual player corrections (wrong club, wrong nationality, name typos) are reviewable, citable, and reproducible.

**Requirements:** R5, R7.

**Dependencies:** Unit 1 (audit produces the issues.csv that seeds the override list).

**Files:**
- Create: `data/manual_overrides/player_corrections.csv` (with header only; populated in Unit 6)
- Create: `data/manual_overrides/README.md` (schema + how to add a row)
- Modify: `tools/build_squad_xg_ratings.py` — apply overrides after the join, before final write
- Test: `tools/test_manual_overrides.py`

**Approach:**
- CSV schema: `entity_type` (player|team|game), `entity_key` (e.g., `nation=Spain;player=Pablo Sarabia García`), `field`, `old_value`, `new_value`, `source_url`, `reason`, `reviewed_by`, `reviewed_date`.
- Apply step: filter overrides to `entity_type='player'` for the squad build; for each, locate the row by `entity_key`, assert `old_value` matches current value (loud failure if drift), set `new_value`.
- Loud failure on `old_value` drift is intentional: if upstream data changed, the human must re-review the correction.
- Validation: every row must have `source_url` and `reason` non-empty (enforced at apply time).

**Patterns to follow:**
- DEVELOPMENT.md's "Subjective adjustments" requirement — every entry needs evidence and reasoning, just at row granularity instead of MODEL.md granularity.

**Test scenarios:**
- Happy path — Override `(nation=Spain; player=Foo)` `club: A → B` is applied; resulting parquet shows `club=B`.
- Edge case — `old_value` mismatch: apply step raises a clear error naming the row, and the build aborts.
- Edge case — Override targets an entity_key that doesn't exist: warning logged, build continues, audit picks it up next run.
- Edge case — Empty `source_url` or `reason`: validation rejects on load.
- Integration — Override layer changes a player's nationality; downstream `team_attack_ratings` reflects the move (player counted under new nation).

**Verification:**
- Empty overrides file leaves all derived data unchanged (regression-safe to add the layer).
- Adding one override and rebuilding changes exactly the targeted row.

---

- [ ] **Unit 6: Player corrections sweep — verify suspicious rows online and patch**

**Goal:** Walk every High/Medium-severity row in the audit's `issues.csv` (after Units 2–5 systemic fixes), verify on authoritative sources, and add override rows. When uncertain, apply the best-known correction with reasoning.

**Requirements:** R5.

**Dependencies:** Units 1, 2, 3, 4, 5.

**Files:**
- Modify: `data/manual_overrides/player_corrections.csv`
- Create: `results/audits/<date>/corrections_log.md` — narrative of each lookup with citations

**Approach:**
- For each remaining issue:
  1. Load the row from the parquet.
  2. Look up the player on Wikipedia (squad page for the nation), Transfermarkt, and one tiebreaker.
  3. If the source agrees with current data → mark as audit Whitelist (record in `corrections_log.md`, no override row).
  4. If the source disagrees → add override row with `source_url` set to the most authoritative source.
  5. If sources disagree → pick the most recent + most authoritative, document conflict in `reason`.
  6. If no source can be found → apply best-effort correction (likely "set to NaN / drop the field") with `reason: "no authoritative source found, defaulting to <X> to avoid biasing model"`.
- Categories likely to need patches:
  - `name_encoding_drift` (e.g., `M''Baye` → `M'Baye`).
  - Players with `nation_x` listed but actually capped by `nation_y` (rare; usually dual nationals).
  - Players with retired status who are still in the squad scrape.
  - GKs with non-zero attack stats (verify).
- Cap: target zero remaining unexplained High-severity audit issues. Medium-severity issues either patched or explicitly accepted in `corrections_log.md`.

**Execution note:** Lookup work is research, not code. The output is data rows, not a feature.

**Patterns to follow:**
- One row per decision, one citation per row, mirrors the override CSV schema.

**Test scenarios:**
- *Test expectation: none — this unit produces data rows and a narrative log, not new logic. The `tools/test_manual_overrides.py` from Unit 5 already tests the apply path; this unit's correctness is reviewed by the contributor sign-off on the corrections_log.md.*

**Verification:**
- Re-running `tools/audit_data_quality.py` produces an `issues.csv` with zero High-severity rows that aren't in the whitelist.
- `corrections_log.md` has one entry per audit issue.

---

- [ ] **Unit 7: Re-run, verify, and document**

**Goal:** Run the full pull → derive → audit pipeline end-to-end on a clean clone, confirm the cleansed data feeds models without breaking them, and document the cleanse in `methodology/`.

**Requirements:** R1, R6, R7.

**Dependencies:** Units 1–6.

**Files:**
- Modify: `methodology/_data-cleanse/README.md` (documents what changed, the shrinkage prior, how to re-run)
- Modify: `DEVELOPMENT.md` (one-paragraph addition under "Architecture" pointing to the cleanse method and the audit folder)
- Modify: `docs/solutions/raw/` (add a solution file capturing learnings — outliers, the multi-club pattern, the override design)

**Approach:**
- Run `python3 tools/aggregate_statsbomb_players.py && python3 tools/pull_understat_players.py && python3 tools/build_squad_xg_ratings.py && python3 tools/audit_data_quality.py` from a clean tree.
- Run `python3 wc2022_xg_backtest.py`. Compare the resulting log-loss / Brier / accuracy against the pre-cleanse numbers in the existing backtest output. Cleansed data should not regress these metrics by more than 0.01 log-loss; if it does, investigate before merging (likely a sign that some "outlier" was actually signal).
- Run `python3 tools/weekly_pull.py 2026-05-06` and verify the comparison table builds without errors.
- Write the methodology doc.

**Test scenarios:**
- Happy path — End-to-end pipeline runs to completion with exit code 0 from a fresh clone.
- Integration — `wc2022_xg_backtest.py` log-loss does not regress more than 0.01 vs current baseline (1.054 for ensemble-v2). If it does, the regression is documented and either accepted with reasoning or treated as a defect.
- Integration — Audit's final issues.csv has zero unexplained High-severity rows.

**Verification:**
- Fresh-clone reproducibility verified.
- Backtest metrics within 0.01 log-loss of baseline.
- Methodology doc and solution writeup present.

## System-Wide Impact

- **Interaction graph:** Touches the data pipeline (`tools/pull_*`, `tools/build_*`, `tools/aggregate_*`) and any model that reads `data/derived/squad_xg_ratings.parquet` or `team_attack_ratings.parquet`. New columns (`is_wc2026_qualifier`, `nat_xg_per_90_shrunk`, `club_history`) are additive; existing columns retained.
- **Error propagation:** Override-apply failures are loud (raise on `old_value` drift) — that's intentional. Audit script is best-effort: never raises, only emits issues. Build scripts continue to fail loudly on missing inputs (current behavior unchanged).
- **State lifecycle risks:** No persistent state added. Audit output is per-date snapshots. Override CSV is git-tracked, so changes are reviewable.
- **API surface parity:** Parquet schemas gain columns, never lose them. Existing model code that reads `blended_xg90` continues to work — it just gets cleaner numbers. Code that reads `club` continues to work — it gets a clean string instead of "A,B".
- **Integration coverage:** Unit 7 regression-tests the backtest; without that, individual unit tests would not catch a quietly-worse model.
- **Unchanged invariants:** `0.4 × nat + 0.6 × club` blend formula. `min 200 minutes` Understat filter. `xi ∈ [0.001, 0.003]` Dixon-Coles time decay. The 8-column predictions schema. The `NAME_TO_FIFA3` mapping. The Kalshi/Polymarket pipelines.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Shrinkage prior over-corrects legitimate elite scorers | Position-aware prior using cohort 99th percentile; backtest regression check in Unit 7; whitelist mechanism in audit |
| Manual corrections introduce reviewer bias (favoring known players) | Override schema mandates `source_url` + `reason`; reviewer initials tracked; spot audit during PR review |
| Online lookups stale by tournament time | Each override row records `reviewed_date`; Unit 7 doc instructs re-running the cleanse close to tournament start |
| Backtest regression after cleanse signals real signal lost | Unit 7 explicitly checks log-loss delta; if > 0.01, halt and investigate; a regression typically means some "outlier" was real |
| Multi-club fix changes `club_minutes_2425` arithmetic | Unit 3 preserves the existing summation; the canonical-club selection only affects `club` string and `club_xg_per_90` weighting |
| Future contributors don't know about the override layer | Unit 7 adds a paragraph to `DEVELOPMENT.md` and a solution file to `docs/solutions/` |

## Documentation / Operational Notes

- `methodology/_data-cleanse/README.md` — the new canonical doc for cleanse rules. New contributors who see weird `xg_per_90` values land here.
- `data/manual_overrides/README.md` — schema + how to add a correction. Linked from `DEVELOPMENT.md`.
- `docs/solutions/raw/2026-05-06-data-cleanse-learnings.md` — captures small-N inflation, multi-club join, qualifier scope as patterns to watch for in future data sources.

No deployment / rollout concerns — this is offline data tooling. No environment variables required. No third-party services beyond what's already in the pipeline.

## Sources & References

- Existing pipeline: `tools/build_squad_xg_ratings.py`, `tools/aggregate_statsbomb_players.py`, `tools/pull_understat_players.py`, `tools/pull_wc2026_squads.py`, `tools/weekly_pull.py`
- Existing data: `data/derived/squad_xg_ratings.parquet`, `understat_player_xg.parquet`, `sb_player_summary.parquet`, `statsbomb_team_xg.parquet`, `statsbomb_player_xg.parquet`, `team_attack_ratings.parquet`
- Project standards: `DEVELOPMENT.md` (Subjectivity and bias policy, Reproducibility standard, Prediction integrity checks)
- External (used in Unit 6 lookups, not at planning time): Wikipedia squad pages, Transfermarkt, FIFA confirmed-qualifiers page
