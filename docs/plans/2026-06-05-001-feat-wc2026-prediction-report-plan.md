---
title: "feat: WC2026 per-game predictions + fun data-backed tournament report"
type: feat
status: active
date: 2026-06-05
---

# feat: WC2026 per-game predictions + fun data-backed tournament report

## Overview

We already have a working Monte Carlo tournament simulator (`tools/simulate_wc2026_duckdb.py`) wired to the curated DuckDB ratings. It emits stage-advancement probabilities (`probabilities.csv`) and a single modal-path bracket (`modal_bracket.json`). The current model's champion ranking is **France ~16%, Argentina ~13%, Portugal ~9%** — notably *not* the user's Spain/Netherlands hunch, which we preserve on purpose (no biasing toward a desired answer).

This plan adds three things on top of that engine:

1. **Per-game probabilities** — a clean 1X2 table for every one of the 72 group fixtures plus every knockout match along the modal path, with expected goals and a qualitative "match character" tag.
2. **A fun, data-backed narrative report** (`REPORT.md`) — group-by-group commentary, what the model expects in each knockout round, and a closing narrative on the projected final (open game? tight? penalties?).
3. **Narrative color from economic + player data** — GDP/population as flavor ("the $4k-GDP giant-killers") and top-xG players per team as "the men who carry each contender." These do **not** enter the prediction engine (see Key Technical Decisions).

The prediction engine itself is **unchanged**: it stays on football signals only (FIFA points, xG attack/defense, recent form), the configuration validated in the WC2022 backtest.

## Problem Frame

The user wants a single, fun, easy-to-read report that: predicts every game with probabilities, names a likely World Cup winner, and narrates each knockout phase and the final — all backed by the data already in `data/wc2026.duckdb` (economic, player, and team). The hard constraint, stated twice, is **do not bias the results**: the user *thinks* it's between Spain, Netherlands, Argentina, and Portugal, but explicitly wants the model to speak for itself.

The engine and Monte Carlo machinery already exist and are validated. The missing pieces are an explicit per-game probability artifact and a narrative layer that turns raw simulation output into readable, data-grounded storytelling.

## Requirements Trace

- **R1.** Produce a probability for every single match (1X2 for all 72 group fixtures; modal-path matchups for knockouts).
- **R2.** Provide a single most-likely World Cup winner plus the champion-odds table.
- **R3.** Use the economic, player, and team data in DuckDB — economics and players as narrative color, team ratings as the engine (per user's two answers during planning).
- **R4.** Funny, easy-to-read group-stage descriptions.
- **R5.** Model's expectation for each knockout phase (R32 → final).
- **R6.** A closing narrative on the final: open match / tight game / penalties — derived from data, not vibes.
- **R7.** Do not bias toward Spain/Netherlands/Argentina/Portugal; report what the model actually says, including where it disagrees with the popular hunch.

## Scope Boundaries

- **Not** changing the prediction engine, ensemble weights, or rating inputs. The football model stays as-is.
- **Not** adding economics or GDP as a predictive feature (explicitly rejected during planning to avoid biasing against GDP-overperformers like Argentina, Morocco, Senegal).
- **Not** rebuilding team attack/defense from a fresh per-player aggregation — we verify the existing ratings already fold in player xG and surface players as narrative only.
- **Not** producing betting recommendations, edge calculations, or market comparison — this is a prediction/storytelling deliverable, not the edge-comparison role (07).
- **Not** a live/in-tournament refresh — this is a pre-tournament snapshot off current DuckDB state.

### Deferred to Separate Tasks

- Live in-tournament re-runs (xG updates after group stage): covered by the separate `pull_wc2026_live.py` effort (see memory: WC2026 live pipeline plan).
- Conditional knockout probabilities for *every possible* matchup (not just the modal path): future iteration if richer bracket viz is wanted.

## Context & Research

### Relevant Code and Patterns

- `tools/simulate_wc2026_duckdb.py` — the engine. `ensemble_probs(home, away)` already returns `(pH, pD, pA, lam_h, lam_a)` per match; `monte_carlo()` produces stage probabilities; `modal_path()` produces the deterministic bracket with concrete knockout matchups. The per-game layer reuses `ensemble_probs` directly — no re-derivation.
- `results/wc2026-sim-duckdb/probabilities.csv` and `modal_bracket.json` — existing outputs the report reads.
- `data/wc2026/tournament.json` — 12 groups, 72 fixtures, full bracket (`r32`, `r16`, `quarterfinals`, `semifinals`, `third_place`, `final`), and `third_place_rules`. `NAME_TO_CODE` in the simulator bridges display names ↔ FIFA codes.
- `tools/lib/` — existing helper module location for shared DuckDB query helpers.
- `tools/tests/` — existing pytest location (`test_pull_espn_wc2026_squads.py` is the pattern to mirror).

### DuckDB tables this work reads (read-only)

- `curated.dim_team_current` — FIFA rank/points, **`gdp_per_capita_usd_latest`, `population_latest`** (economic color), confederation.
- `curated.fact_team_rating` — `attack` / `defense` / `recent_form` (the engine inputs; already squad-xG-derived — verified in Unit 1).
- `curated.fact_player_xg_per_90` — `blended_xg_per_90`, `national_team_xg_per_90`, `key_passes_per_90` per `player_id`/`team_code` (star-player narrative).
- `curated.dim_player` — `display_name`, `position`, `current_club` for naming the stars.
- `curated.fact_team_economics` — historical GDP/population if richer econ color is wanted.

### Institutional Learnings

- `docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md` — **Model Disagreement Taxonomy.** When all three component models (Elo / Form / xG-Poisson) agree → "Golden Zone" (15/15 correct in the WC2022 backtest, even at 48% confidence). Three-way split → noise, genuinely a coin-flip. **We reuse this taxonomy as the data-backed basis for "match character":** agreement → confident call; split → "this one's a coin-flip, expect extra time / penalties." This is the honest, validated way to answer R6.
- Memory `feedback_no_hardcoded_modeling_weights` — tier weights and project-wide *predictive* priors live in `db/masters/*.csv`, never as code literals. **Applies here only as a guardrail:** match-character thresholds are *presentation* classification, not predictive priors, so they may stay as named constants in the report module — but we must label them as presentational and introduce **no** new predictive weights.
- Memory `feedback_player_identity_registry` (MDM) — read facts, never extend masters from them. The narrative extractors are strictly read-only.

### External References

- None required. The engine is validated locally; the work is output/narrative layering over existing, well-patterned code.

## Key Technical Decisions

- **Engine untouched; economics/players are narrative-only.** Per the user's two planning answers. Keeps the model honest and avoids systematically downgrading CONMEBOL/CAF teams that overperform their GDP. Economics and players are read *after* simulation, purely for color.
- **Reuse `ensemble_probs` for per-game output — do not recompute.** The 1X2 probabilities the report needs are already computed inside the engine; the per-game layer calls the same function so the table and the simulation can never disagree.
- **Knockout per-game probabilities are reported along the modal path only.** Group fixtures are fixed, so all 72 get exact 1X2. Knockout opponents are contingent, so we report the modal-path matchup (who the model expects to actually meet) rather than an intractable all-pairs matrix. Stage-advancement odds (already in `probabilities.csv`) cover the contingent view.
- **"Match character" = model-disagreement taxonomy + expected goals.** Character is derived from (a) whether Elo/Form/Poisson agree (confidence) and (b) `lam_h + lam_a` (open vs tight) and (c) closeness of pH vs pA (coin-flip → penalty-prone). This grounds every "open / tight / penalties" claim in numbers, reusing the validated WC2022 taxonomy.
- **New presentational constants are labeled, not modeling weights.** Thresholds like "total expected goals > 3.0 → goal-fest" are classification cutoffs for prose, carry a comment saying so, and introduce no predictive priors — respecting the no-hardcoded-weights guardrail.
- **Report is regenerable and seed-stable.** `REPORT.md` is built from committed/seeded outputs; same seed → same report. The report states the seed and run size for reproducibility.

## Open Questions

### Resolved During Planning

- Economics in the engine? → No. Narrative color only (user choice).
- Player data depth? → Verify existing ratings already use player xG; surface stars as narrative (user choice).
- Whose champion does the report name? → Whatever the model says (currently France), with an explicit, friendly note that it disagrees with the Spain/Netherlands popular hunch — honoring "do not bias."

### Deferred to Implementation

- Exact column order / filenames for the per-game CSV — settle when wiring the writer.
- Whether the report embeds a small ASCII bracket or links to `modal_bracket.json` — decide when drafting `REPORT.md` for readability.
- Final wording/tone calibration of the "funny" group blurbs — a drafting concern, not an architectural one.

## Implementation Units

- [x] **Unit 1: Verify rating lineage and document the data the engine actually uses**

**Goal:** Confirm (and write down) that `curated.fact_team_rating` attack/defense values are derived from squad/player xG, so the report can truthfully claim "team data + player data drive the engine," and so we know players are already represented before adding star-player color.

**Requirements:** R3, R7

**Dependencies:** None

**Files:**
- Modify: `results/wc2026-sim-duckdb/` (add a short `DATA_LINEAGE.md` note) — or append a lineage section to the report later; decide in Unit 5.
- Test: none — verification + documentation only.

**Approach:**
- Trace `fact_team_rating` provenance via the build tools (`tools/build_squad_xg_ratings.py`, `tools/build_2026_ratings.py`) and confirm attack/defense originate from aggregated player xG.
- Record the lineage in one short paragraph the report can cite: which curated tables feed the engine, and that economics/players are color-only.

**Patterns to follow:** `db/SCHEMA.md` lineage prose style.

**Test scenarios:**
- Test expectation: none — documentation/verification unit with no behavioral change.

**Verification:** A reviewer can read the lineage note and see, table-by-table, what feeds the engine vs. what is narrative color.

---

- [x] **Unit 2: Match-character classifier (pure function)**

**Goal:** A deterministic function that turns one match's model outputs into a qualitative character label used by both the per-game table and the report.

**Requirements:** R6

**Dependencies:** None

**Files:**
- Create: `tools/lib/match_character.py`
- Test: `tools/tests/test_match_character.py`

**Approach:**
- Input: `(pH, pD, pA, lam_h, lam_a)` plus the three component-model picks (Elo/Form/Poisson) so we can compute model agreement (the WC2022 taxonomy).
- Output: a small struct — `favorite`, `confidence_band` (golden-zone / 2-way / 3-way-split), `openness` ("goal-fest" / "balanced" / "low-scoring grind" from `lam_h+lam_a`), and `decisiveness` ("comfortable" / "competitive" / "coin-flip → extra-time/penalties" from |pH−pA| and pD).
- Thresholds are named, commented as **presentational classification cutoffs, not predictive weights**.

**Patterns to follow:** the disagreement taxonomy in the WC2022 backtest solution doc; keep it a pure function (no DB, no I/O) for easy testing.

**Test scenarios:**
- Happy path: clear favorite (pH=0.70, low draw, lam 2.4/0.8) → favorite=home, decisiveness="comfortable", openness="goal-fest".
- Edge case: near coin-flip (pH=0.34, pA=0.33, pD=0.33, lam 1.0/1.0, three different model picks) → confidence_band="3-way-split", decisiveness="coin-flip → penalties".
- Edge case: low-scoring tight game (pH=0.45, pA=0.40, lam 0.7/0.6) → openness="low-scoring grind", decisiveness="competitive".
- Edge case: all three models pick the same side at modest confidence (pH=0.52) → confidence_band="golden-zone".
- Edge case: boundary values exactly on a threshold resolve deterministically (document which side of the cutoff wins).

**Verification:** Unit tests pass for each band; the same inputs always yield the same label.

---

- [x] **Unit 3: Per-game probability emitter**

**Goal:** Write a per-game 1X2 table covering all 72 group fixtures and every modal-path knockout match, with expected goals and the Unit 2 character label.

**Requirements:** R1, R2

**Dependencies:** Unit 2

**Files:**
- Modify: `tools/simulate_wc2026_duckdb.py` (add a per-game collection + writer; reuse `ensemble_probs` and the existing `modal_path` knockout matchups)
- Create: `results/wc2026-sim-duckdb/per_game.csv`
- Test: `tools/tests/test_per_game_emit.py`

**Approach:**
- Group stage: iterate all 12 groups × 6 fixtures from `tournament.json`, call `ensemble_probs` per fixture, write `stage, group, date, home, away, p_home, p_draw, p_away, lam_home, lam_away, exp_total_goals, favorite, character`.
- Knockouts: walk the modal-path matchups already computed in `modal_path()` (R32→Final), emit the same columns with the realized matchup and the round label.
- Probabilities are normalized (sum ≈ 1.0); reuse the engine's normalization so the table matches the simulation exactly.

**Execution note:** Start with a failing test asserting 72 group rows + the modal knockout count, then wire the emitter.

**Patterns to follow:** existing CSV writer in `simulate_wc2026_duckdb.py:main()` (`probabilities.csv`).

**Test scenarios:**
- Happy path: exactly 72 group rows present (12 groups × 6 matches), every `home`/`away` resolves to a known FIFA code.
- Happy path: each row's `p_home + p_draw + p_away` ≈ 1.0 (within 1e-6).
- Integration: knockout rows match the modal bracket — the R32 matchups in `per_game.csv` equal those in `modal_bracket.json`.
- Edge case: a team with fallback (median) ratings still produces valid, normalized probabilities (no NaN).
- Reproducibility: same `--seed` → byte-identical `per_game.csv`.

**Verification:** `per_game.csv` exists with all group fixtures + modal knockouts; probabilities normalized; matchups consistent with the modal bracket.

---

- [x] **Unit 4: Narrative context extractors (economics + star players)**

**Goal:** Read-only DuckDB helpers that supply the report's color: top-xG players per team and economic facts per team.

**Requirements:** R3, R4

**Dependencies:** None

**Files:**
- Create: `tools/lib/wc2026_context.py`
- Test: `tools/tests/test_wc2026_context.py`

**Approach:**
- `top_players(team_code, n=3)` → query `curated.fact_player_xg_per_90` joined to `dim_player`, order by `blended_xg_per_90`, return name/position/club/xg90. Graceful fallback to `[]` when a team has no player rows.
- `team_econ(team_code)` → from `dim_team_current`: `gdp_per_capita_usd_latest`, `population_latest`, `fifa_rank`, `confederation`. Used for lines like "the $4k-GDP, 525k-population side punching 100× their weight."
- Strictly read-only; never writes to DuckDB (MDM discipline).

**Patterns to follow:** read-only `duckdb.connect(..., read_only=True)` pattern from `simulate_wc2026_duckdb.py:load_ratings()`.

**Test scenarios:**
- Happy path: `top_players('ESP')` returns ≤3 rows sorted descending by xg90, each with a non-empty name.
- Edge case: team with no player xG rows → returns `[]`, not an error.
- Edge case: `team_econ` for a team with NULL GDP (e.g., a 2025 row) falls back to the latest non-null year or returns `None` gracefully.
- Happy path: `team_econ('ARG')` returns populated GDP/population/fifa_rank.

**Verification:** Helpers return clean structs for contenders and degrade gracefully for data-poor teams; no writes occur.

---

- [x] **Unit 5: Fun narrative report generator**

**Goal:** The deliverable — a single readable `REPORT.md` that names the likely winner, narrates all 12 groups with humor, lays out the model's expectation for each knockout round, and closes with a data-backed description of the projected final.

**Requirements:** R2, R4, R5, R6, R7

**Dependencies:** Units 2, 3, 4

**Files:**
- Create: `tools/build_wc2026_report.py`
- Create: `results/wc2026-sim-duckdb/REPORT.md` (generated output)
- Test: `tools/tests/test_build_wc2026_report.py`

**Approach:**
- Inputs: `probabilities.csv` (stage odds), `modal_bracket.json` (the projected path), `per_game.csv` (per-match 1X2 + character), and the Unit 4 extractors (econ + stars).
- Structure:
  - **Headline:** the model's champion + champion-odds top-8 table. An explicit, friendly "the model disagrees with the popular Spain/Netherlands hunch — here's why" callout (honors R7).
  - **The 12 groups:** per group, projected 1-2-3, the funniest data hook (biggest favorite, likeliest upset by win-prob, an econ/David-vs-Goliath line), 2-3 sentences each.
  - **Knockout rounds R32 → SF:** what the model expects each round — survival odds, the marquee modal matchup, and any "coin-flip" games flagged by match character.
  - **The Final:** the modal finalists, their head-to-head ensemble 1X2, star men from Unit 4, and a character verdict — open game / tight / penalty-bound — pulled straight from Unit 2's label, not invented.
  - **Caveats footer:** seed, run size, that economics/players are color-only, and a one-line calibration note (Golden-Zone games are near-locks; 3-way-splits are genuine coin-flips).
- Tone: fun and punchy, but every adjective is backed by a number already in the artifacts.

**Patterns to follow:** existing results-dir markdown (e.g., any `MODEL.md`), and the WC2022 taxonomy for confidence language.

**Test scenarios:**
- Happy path: report contains all 12 group sections and all knockout rounds (R32, R16, QF, SF, Final).
- Integration: the champion named in the headline equals the top team in `probabilities.csv` and the `modal_bracket.json` champion (they must agree).
- Integration: the Final section's 1X2 numbers match the corresponding `per_game.csv` knockout row.
- Edge case: a contender with no star-player data still renders its section (extractor fallback) without crashing.
- Happy path: output is non-empty valid markdown and mentions the seed + run size.

**Verification:** Running the generator after a simulation produces a complete, internally-consistent `REPORT.md` whose headline winner, bracket, and per-game numbers all agree.

## System-Wide Impact

- **Interaction graph:** New read-only consumers of `data/wc2026.duckdb` and the existing results artifacts. The engine (`monte_carlo`, `modal_path`, `ensemble_probs`) is reused, not modified in behavior — Unit 3 only *adds* an output path.
- **Error propagation:** Extractors degrade gracefully (empty lists / None) so a data-poor team never breaks the report. The simulator's existing median-fallback for missing ratings is preserved.
- **State lifecycle risks:** All new writes target `results/wc2026-sim-duckdb/` (regenerable outputs). No DuckDB writes, no master edits — MDM discipline intact.
- **API surface parity:** `per_game.csv` becomes a new published artifact alongside `probabilities.csv`; document it in the results dir so downstream roles (07 edge-comparison) can consume it later.
- **Unchanged invariants:** The prediction engine, ensemble weights (0.35/0.45/0.20), and rating inputs are explicitly unchanged; champion probabilities for a given seed remain identical to today's run.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Report reads as "fun" but smuggles in bias toward a desired winner | Headline names the model's actual champion and explicitly flags disagreement with the Spain/Netherlands hunch; every claim cites a number from the artifacts |
| Economics accidentally influences predictions | Economics is read only in Units 4-5, after simulation; engine code path never imports the econ extractors |
| New "character" thresholds drift into looking like modeling weights | Labeled as presentational classification cutoffs in code comments; no new predictive priors introduced (guardrail from `feedback_no_hardcoded_modeling_weights`) |
| Per-game table and simulation disagree | Unit 3 reuses `ensemble_probs` directly and a test asserts knockout matchups equal `modal_bracket.json` |
| Star-player claims wrong for teams with thin data | Extractor fallback returns empty; report omits the star line rather than fabricating |

## Documentation / Operational Notes

- Add a short README/section in `results/wc2026-sim-duckdb/` describing the three artifacts (`probabilities.csv`, `per_game.csv`, `REPORT.md`) and the seed/run-size used.
- Run order: `python3 tools/simulate_wc2026_duckdb.py --n 20000 --seed 42` (now also writes `per_game.csv`) → `python3 tools/build_wc2026_report.py` → `REPORT.md`.

## Sources & References

- Engine: `tools/simulate_wc2026_duckdb.py`
- Data contract: `db/SCHEMA.md`
- Tournament structure: `data/wc2026/tournament.json`
- Confidence/character basis: `docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md`
- Existing outputs: `results/wc2026-sim-duckdb/probabilities.csv`, `results/wc2026-sim-duckdb/modal_bracket.json`
