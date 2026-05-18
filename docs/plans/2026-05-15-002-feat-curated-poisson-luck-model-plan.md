---
title: "feat: curated-poisson-luck — DuckDB-native goals model with per-game luck factor"
type: feat
status: completed
date: 2026-05-15
---

# feat: curated-poisson-luck — DuckDB-native goals model with per-game luck factor

## Overview

A new statistical model — `curated-poisson-luck` — that predicts WC2026 match outcomes and runs the tournament Monte Carlo using **only** tables in the `curated` schema of `data/wc2026.duckdb`. The model is a Poisson goals model whose team scoring rate `λ_team` is built from:

1. Recent form (`curated.dim_team_recent_form`) — last-10 and competitive-last-10 goals scored / conceded.
2. Per-match history (`curated.fact_international_match`) — used to estimate each team's mean and standard deviation of goals scored, weighted by tournament tier.
3. FIFA ranking (`curated.fact_team_fifa_ranking`, via `curated.dim_team_current`) — as a shrinkage prior for thin-sample teams.
4. Country economics (`curated.fact_team_economics`, via `curated.dim_team_current`) — `gdp_per_capita_usd_latest` and `population_latest` as a small structural prior.

On top of `λ_team`, every simulated match adds a **per-game luck factor**: a perturbation `ε ~ Normal(0, σ_team)` truncated to `[-2σ_team, +2σ_team]`. Goals are then sampled `g ~ Poisson(max(0.05, λ_team + ε))`. The luck factor enters both the per-match predictions in `predictions.csv` (closed-form probabilities) and the tournament Monte Carlo (sample-based).

## Problem Frame

The existing models in `results/` either (a) read parquet files directly (`tools/simulate_wc2026.py`, `ensemble_model.py`), bypassing the new DuckDB layer the project just stood up, or (b) consume a single rating source (`team_attack_ratings.parquet`) that pre-dates the unified curated schema. The newly-curated facts — `fact_international_match`, `fact_team_economics`, `fact_team_fifa_ranking` — and the denormalized read views (`dim_team_current`, `dim_team_recent_form`) are not yet exercised end-to-end by any model. This plan validates that surface, demonstrates the modeling pattern downstream consumers should follow, and adds explicit goal-variance modeling that no current model represents.

## Requirements Trace

- R1. The model must read only from `curated.*` tables/views in `data/wc2026.duckdb` — no parquet reads, no manual CSV inputs, no external HTTP fetches at runtime.
- R2. Inputs must include team form, per-match historical results, FIFA ranking, and country economic data (GDP per capita + population) — all sourced from curated tables.
- R3. Each simulated game must apply a luck factor: a perturbation to expected goals bounded at ±2 standard deviations of the team's historical goals-scored distribution.
- R4. Match-level predictions (`predictions.csv`) must follow the existing schema: `as_of_date, match_id, market_type, outcome, p_model, confidence, model_version, notes`, with probabilities summing to ~1.0 per `(match_id, market_type)`.
- R5. Tournament-level outputs (`probabilities.csv`) must follow the existing `results/wc2026-sim/probabilities.csv` shape: `team, p_champion, p_final, p_semi, p_qf, p_r16, p_r32`.
- R6. The model must be registered as a row in `curated.dim_model` via an updated `db/masters/models.csv` and a `MODEL.md` card, so `dim_model` stays in sync.
- R7. The simulator must respect the 12-group × 4 → top-2 + best-8-thirds → R32 bracket structure already encoded in `data/wc2026/tournament.json`.

## Scope Boundaries

- **Not** a replacement for the ensemble, Elo, Poisson-goals, or any other existing model. This is one more independent model that the ensemble could later weight in.
- **Not** modifying the curated schema. No new dim or fact tables. Only one optional read-time view is added in Unit 1 — and that view is justified only if the goal-stats CTE is reused outside the model.
- **Not** changing `tools/build_duckdb.py` or any of the staging / quarantine / matching layers.
- **Not** adding new external data sources. GDP and population are already in `fact_team_economics`; FIFA ranks are already in `fact_team_fifa_ranking`.
- **Not** a backtest. WC2022 backtesting against this model is deferred (see below).

### Deferred to Separate Tasks

- **WC2022 backtest of `curated-poisson-luck`**: held-out validation that proves the model's per-match log-loss / Brier and assesses whether the luck factor improves or degrades calibration. Tracked separately; the model card will report `confidence = medium` until a backtest lands.
- **Inclusion in the ensemble**: weighting this model into `ensemble-v2` / `ensemble-e3` happens only after the backtest, per the [WC2022 backtest learnings](../solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md) policy.
- **Temporal FIFA-rank join**: `dim_team_recent_form.avg_opponent_fifa_rank_last_10` already documents this caveat — the FIFA-rank fact is snapshot-only today. Strength-of-schedule remains "current opponent rank" for now.

## Context & Research

### Relevant Code and Patterns

- `methodology/_template/model.py` — reference shape for `predictions.csv` output (seed setup, `OUT_DIR`, row schema). The new model's `model.py` mirrors this.
- `tools/simulate_wc2026.py` — reference structure for tournament traversal: `sim_group → pick_third_place_qualifiers → sim_bracket`. The new simulator borrows the bracket walker but replaces the rating-driven `get_lambda` with a curated-features-driven `λ_team` lookup plus the luck factor.
- `db/queries/examples/team_features_for_modeling.sql` — canonical read pattern for FIFA + economics features.
- `db/queries/examples/team_form_for_modeling.sql` — canonical read pattern for recent-form features.
- `db/queries/examples/team_recent_results.sql` — canonical pattern for per-team match unpivot from `fact_international_match`.
- `data/wc2026/tournament.json` — group structure, bracket slot rules, third-place qualifier slot map.
- `results/poisson-goals/MODEL.md` — MODEL.md card template to follow.

### Institutional Learnings

- `feedback_player_identity_registry.md` (MDM rule): facts join to dims on stable codes only; the model does **not** name-match teams. All joins use `team_code` (FIFA 3-letter).
- `wc2022_backtest_learnings.md`: log-loss target to beat eventually is `ensemble-v2 = 1.054`. Form was the strongest single predictor (46.9% accuracy). xG-Poisson underperformed due to sparse training data — a relevant warning for this model, which is why this design weights form heavily and uses FIFA rank as a shrinkage prior for thin-sample teams.
- `data-gaps-roadmap.md` notes ~15 teams (Ghana, Cape Verde, Haiti, Bosnia, etc.) have sparse historical samples — confirmed by the per-team match-count check during planning (Ghana 21 matches since 2022, Haiti 16). The shrinkage prior is the design response.

### External References

None — entirely codebase-internal. The Poisson goals model and truncated-normal perturbation are standard techniques.

## Key Technical Decisions

- **Decision 1: λ_team is a weighted blend, not a pure form average.**
  Rationale: thin samples (Haiti = 16 matches since 2022) over-fit form. Final `λ_team = w_form · form_λ + w_fifa · fifa_λ + w_econ · econ_λ`, with `w_form` growing as the team's match count grows. Specific weights are stated in Unit 3, not here, because they are a model-tuning concern. The structure is the decision.
- **Decision 2: σ_team is estimated from the same goals-scored sample used for `form_λ`.**
  Rationale: keeping mean and std on the same sample means the 2σ bound is internally consistent. A team with no history gets a global-σ fallback (cohort median).
- **Decision 3: Luck factor is additive, truncated-Normal, applied per game per team independently.**
  Rationale: additive perturbation on λ before sampling Poisson is interpretable as "good day / bad day" — it widens the goal distribution above what raw Poisson allows (which is mean = variance, often too narrow for international football where goal variance > mean). Truncation at ±2σ keeps freak draws bounded. Independent per-team-per-game preserves the assumption that the two teams' goal processes are independent (same as Dixon-Coles before correlation correction).
- **Decision 4: Goal stats come from a model-local CTE, not a new curated view, unless reused.**
  Rationale: the project's MDM discipline says no new facts unless an authoritative source motivates them. Goal stats are a derived computation off `fact_international_match`. If the same query gets reused by future models, we promote it to a `curated.dim_team_goal_stats` VIEW in a separate PR. For now, the CTE lives inside the model's `model.py` (or a `.sql` file under `methodology/curated-poisson-luck/queries/`).
- **Decision 5: Economics enters as a small, monotone log-scaled multiplier on λ_team, capped.**
  Rationale: `log10(gdp_per_capita_usd_latest)` ranges ~3 → ~5 across the qualifier pool. A capped, centered, low-weight multiplier (e.g., ±10% of the FIFA-prior λ) encodes "rich, large nations slightly outperform their FIFA rank, all else equal" without letting GDP dominate the model. Population enters the same way with a separate, smaller weight. Both are clipped to avoid runaway extremes.
- **Decision 6: Home advantage uses the `neutral_site` flag, not a fixed home boost.**
  Rationale: every WC2026 match has `neutral_site` semantics for non-host teams. The host countries (USA, Mexico, Canada) get a modest home boost; all others use a neutral-site λ. This matches the existing `ensemble_model.py` treatment of home advantage but reads it from the curated `fact_international_match` distribution rather than a hardcoded `+50` Elo.
- **Decision 7: All randomness is seeded via `numpy.random.default_rng(seed)`.**
  Rationale: a single `rng` instance threaded through `sim_match → sim_group → sim_bracket` is reproducible and parallel-safe.

## Open Questions

### Resolved During Planning

- **Where does the luck factor live — closed-form predictions, simulations, or both?** Resolved: both. Closed-form predictions integrate over the truncated-normal perturbation analytically (or by quick numerical integration over a few sigma points); simulations draw a single perturbation per team per game.
- **Should the model fit a Dixon-Coles correlation correction?** Resolved: no, not in v1. The luck factor already widens the marginal distributions; adding ρ is a separate model variant. Documented in Future Considerations of the MODEL.md.
- **Does the model need a per-tournament-tier importance weight on historical matches?** Resolved: yes, but only for `form_λ` and `σ_team` estimation. Tier weights live in a small dict in `model.py` (`tier_1=1.0`, `tier_2=0.9`, `tier_3=0.7`, `tier_4=0.4`). These mirror the existing `IMPORTANCE` dict in `ensemble_model.py` for consistency.

### Deferred to Implementation

- **Exact w_form / w_fifa / w_econ values and the curve for w_form as a function of match count.** Decided during Unit 3 against the calibration target. The plan fixes the structure; the values are an implementation-time tuning.
- **Sigma fallback for teams with zero matches since 2022.** Default proposal: global median σ across all qualifiers. Confirmed during Unit 3.
- **Whether to emit per-match goal-distribution diagnostics for debugging.** A `model_diagnostics.csv` artifact is nice-to-have; decided during Unit 4.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
                    curated.fact_international_match
                                  │
                                  ▼
                       per-team goal stats CTE
                       (gf_mean, gf_std, n)
                                  │
                                  │
   curated.dim_team_recent_form ──┤── form_λ_team (weighted by tier)
                                  │
   curated.dim_team_current   ────┤── fifa_λ_team (rank → expected goals curve)
   (FIFA + economics enriched)    │── econ_multiplier (log-GDP, log-pop, capped)
                                  │
                                  ▼
                  λ_team_baseline (blended, neutral site)
                                  │
                          [host adjustment]
                                  │
                                  ▼
                       λ_team for this game
                                  │
                  per-game luck draw  ε ~ N(0, σ_team)
                  truncated to [-2σ, +2σ]
                                  │
                                  ▼
              g_team ~ Poisson(max(0.05, λ_team + ε))
                                  │
                                  ▼
       match outcome  ─── predictions.csv  (closed-form 1X2)
       group standings ── sim_group()
       bracket walk   ──  sim_bracket()
                                  │
                                  ▼
                          probabilities.csv
                          (per-team stage reach)
```

## Implementation Units

- [ ] **Unit 1: Goal-stats query — `(team_code, n, gf_mean, gf_std, ga_mean, ga_std)`**

**Goal:** Produce, from `curated.fact_international_match` alone, the per-team historical goal-scoring and goal-conceding mean and std-dev, tier-weighted, since 2022-01-01. Used downstream as the `σ_team` input to the luck factor and as one of the inputs to `λ_team`.

**Requirements:** R1, R2, R3

**Dependencies:** None.

**Files:**
- Create: `methodology/curated-poisson-luck/queries/team_goal_stats.sql`
- Create: `db/queries/examples/team_goal_stats_for_modeling.sql` (mirror, registered as a project-level example so future models can reuse it without going through this model's folder)
- Test: `tools/verify_duckdb.py` (extend its assertions block with one row-count and one non-null-check on the new query)

**Approach:**
- Unpivot `fact_international_match` to one row per (team_code, match_date, gf, ga, tournament_tier).
- Apply tier weights (`tier_1=1.0`, `tier_2=0.9`, `tier_3=0.7`, `tier_4=0.4`) as `sample_weight`.
- Compute weighted mean and weighted std-dev per `team_code`.
- Floor `n` at the unweighted count to keep "sample size" honest.

**Patterns to follow:**
- `db/queries/examples/team_recent_results.sql` for the unpivot shape.
- `db/queries/examples/team_features_for_modeling.sql` for the curated-only read discipline.

**Test scenarios:**
- Happy path: ARG, BRA, MEX return `gf_mean` in `[1.2, 2.2]` and `gf_std > 0.8`. Verified against the planning-time SQL probe.
- Edge case: teams with zero post-2022 matches (e.g., a non-qualifier code) are absent from the result, not present with NULL stats — confirms the implicit inner aggregation.
- Edge case: tier weights collapse correctly to ~1.0 for teams whose matches are all `tier_1_world_cup`.
- Integration scenario: result row count equals `(SELECT COUNT(DISTINCT team_code) FROM <unpivot CTE>)` — guards against accidental cross-join inflation.

**Verification:**
- `duckdb data/wc2026.duckdb < methodology/curated-poisson-luck/queries/team_goal_stats.sql` returns one row per qualifier with non-null `gf_mean`, `gf_std`, `ga_mean`, `ga_std` for every team that has ≥1 match since 2022.
- `tools/verify_duckdb.py` exits 0 with the added assertions.

---

- [ ] **Unit 2: Model-input query — wide team-features table for WC2026 qualifiers**

**Goal:** One SQL file that joins `dim_team_current`, `dim_team_recent_form`, and the goal-stats query from Unit 1 into a single wide row per WC2026 qualifier — the canonical model input.

**Requirements:** R1, R2

**Dependencies:** Unit 1.

**Files:**
- Create: `methodology/curated-poisson-luck/queries/team_model_features.sql`

**Approach:**
- `WITH goal_stats AS (...Unit 1 query...)` then `SELECT` everything from `dim_team_current` + `dim_team_recent_form` + `goal_stats`, filtered to `is_wc2026_qualifier = TRUE`.
- One row per `team_code`. Document column origins inline with `-- from ...` comments.
- Explicitly list columns in the final `SELECT` — no `SELECT *` — so downstream Python can pin its column contract.

**Patterns to follow:**
- `db/queries/examples/team_features_for_modeling.sql` (don't replicate, but mirror the docstring style and the explicit-column discipline).

**Test scenarios:**
- Happy path: 48 rows for the 48 confirmed WC2026 qualifiers.
- Edge case: a qualifier with no economics data (e.g., a country World Bank doesn't report) appears in the result with NULL `gdp_per_capita_usd_latest` — confirms the LEFT JOIN inside `dim_team_current` is preserved through this query.
- Edge case: a qualifier with no recent matches still appears with NULL form columns and NULL goal-stats — confirms LEFT JOINs all the way through; downstream Python is responsible for fallbacks.

**Verification:**
- Row count = 48.
- Every WC2026 qualifier from `dim_team` with `is_wc2026_qualifier = TRUE` appears in the result.

---

- [ ] **Unit 3: Model — fit `λ_team`, `σ_team`, and write match-level predictions**

**Goal:** Python module that loads Unit 2's query results, blends `λ_team` from form + FIFA + economics, estimates `σ_team`, generates closed-form 1X2 probabilities for every WC2026 group-stage fixture, and writes `predictions.csv` in the project's standard shape.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Unit 1, Unit 2.

**Files:**
- Create: `methodology/curated-poisson-luck/model.py`
- Create: `methodology/curated-poisson-luck/__init__.py` (empty; keeps the directory importable so the simulator in Unit 4 can re-use helpers)
- Test: `tests/test_curated_poisson_luck_model.py` (small unit-test file alongside the model — `tests/` directory exists at repo root)

**Approach:**
- Connect to `data/wc2026.duckdb` via `duckdb.connect(read_only=True)`.
- Run Unit 2's query, materialize to a pandas DataFrame.
- Compute `λ_team`:
  1. `form_λ = gf_last_10 / matches_last_10` (NULL → fall back to `gf_mean` from goal-stats; still NULL → cohort median).
  2. `fifa_λ` from a simple monotone curve on `fifa_rank` (lower rank → higher λ; calibrated against the cohort `gf_mean` distribution).
  3. `econ_multiplier = 1 + α · clip(z(log10(gdp_per_capita)), -1, 1) + β · clip(z(log10(population)), -1, 1)` with small `α`, `β` (e.g., 0.05, 0.02).
  4. Blend: `λ_team = (w_form(n) · form_λ + (1 - w_form(n)) · fifa_λ) · econ_multiplier`, where `w_form(n) = min(1.0, n / 30)` so a team with 30+ matches relies fully on form, and one with 0 matches relies fully on FIFA prior.
- Compute `σ_team = max(gf_std, 0.4)` (floor avoids degenerate truncation).
- Closed-form 1X2: for each fixture, compute `P(g_h, g_a)` over the joint Poisson with luck-perturbed λ. Either:
  - Integrate ε analytically by quadrature (5–7 sigma points), or
  - Use a simple compound-Poisson approximation: total variance = λ + σ² truncated → match probabilities via a negative-binomial-like marginal.
  Either approach is acceptable as long as the result respects R4 (probabilities sum to ~1.0 within rounding).
- Output `predictions.csv` with required columns; `notes` column documents the model formula and `σ` used.
- `confidence`: `"high"` if both teams have `n ≥ 30`, `"medium"` if both `≥ 10`, else `"low"`.

**Execution note:** Write the unit test in `tests/test_curated_poisson_luck_model.py` first. Drive the design by red-then-green on probability-sum and luck-factor-shape contracts.

**Patterns to follow:**
- `methodology/_template/model.py` for output skeleton and seed handling.
- `ensemble_model.py` for the `IMPORTANCE` tier dict shape.
- `results/poisson-goals/MODEL.md` for the MODEL.md template (created in Unit 5).

**Test scenarios:**
- Happy path: ARG vs HAI returns `p_home > 0.6`, `p_away < 0.15`. Asserts directionality, not exact value.
- Happy path: every fixture's `(p_home + p_draw + p_away)` is within `[0.999, 1.001]`.
- Edge case: a team with zero recent matches (`matches_last_10 IS NULL`) still produces a finite λ via the FIFA prior fallback.
- Edge case: a team with `gf_std IS NULL` (no goal-stats row) uses the cohort-median σ; the resulting probabilities are still well-formed.
- Error path: missing `data/wc2026.duckdb` raises a clear, actionable error before any pandas work.
- Integration scenario: the function that builds `λ_team` returns identical values for the same `team_code` across two consecutive calls in the same seeded run — proves no hidden state.

**Verification:**
- `python3 methodology/curated-poisson-luck/model.py` writes `results/curated-poisson-luck/<today>/predictions.csv` with one row per `(match_id, outcome ∈ {H, D, A})`, ~3 × 72 = 216 rows for the group stage.
- `tests/test_curated_poisson_luck_model.py` passes.

---

- [ ] **Unit 4: Simulator — Monte Carlo tournament with per-game luck draws**

**Goal:** Run N=10,000 Monte Carlo tournaments using λ_team + truncated-Normal luck draws. Output per-team stage-reach probabilities to `probabilities.csv` and a JSON variant.

**Requirements:** R1, R3, R5, R7

**Dependencies:** Unit 3 (re-uses its λ_team / σ_team computation helpers).

**Files:**
- Create: `methodology/curated-poisson-luck/simulate.py`
- Modify: none. The existing `tools/simulate_wc2026.py` is not touched — that simulator stays parquet-driven for now and is a separate model in `results/wc2026-sim/`.

**Approach:**
- Import λ_team / σ_team helpers from `methodology.curated_poisson_luck.model` (rename the package folder to a Python-safe identifier if needed: `curated_poisson_luck` with underscores, while the model_id slug stays kebab-case for filesystem consistency — both are valid; the slug is what gets registered).
- Load `data/wc2026/tournament.json` for the bracket structure.
- For every simulated match:
  1. Draw `ε_home ~ TruncNormal(0, σ_home, ±2σ_home)`, `ε_away ~ TruncNormal(0, σ_away, ±2σ_away)`.
  2. `λ_home_eff = max(0.05, λ_home + ε_home)`, same for away.
  3. Sample `g_home, g_away ~ Poisson(λ_*_eff)`.
  4. For knockout matches: if draw, simulate ET with `λ_*_eff / 3` (30-min ET ≈ 1/3 of 90 min). If still tied, coin-flip on `λ_home_eff / (λ_home_eff + λ_away_eff)` as a penalty-shootout proxy. This mirrors `tools/simulate_wc2026.py` semantics.
- Track per-team stage reach across N runs. Aggregate to `(team, p_champion, p_final, p_semi, p_qf, p_r16, p_r32)`.
- Map tournament JSON team names → `team_code` via `curated.dim_team.team_name` (canonical join). Document the name-resolution table inline; if a name in the JSON has no `dim_team` match (e.g., a placeholder for an unconfirmed qualifier), raise loudly during pre-flight rather than silently fallback.

**Patterns to follow:**
- `tools/simulate_wc2026.py` — `sim_group`, `pick_third_place_qualifiers`, `sim_bracket`, `resolve_r32_slot`. Borrow the bracket walker; replace the rating-based `get_lambda` with the curated-poisson-luck `get_lambda(team_code, rng)` that returns `(λ_eff, σ)` for this team this game.

**Test scenarios:**
- Happy path: with `n=1000, seed=42`, ARG has `p_r16 ≥ 0.85` and `p_champion ≥ 0.04`. Asserts ballpark, not point estimates.
- Happy path: per-team `p_r32 = 1.0` for all 48 qualifiers (every team starts in the group stage — this catches a class of slot-resolution bugs).
- Happy path: `Σ p_champion = 1.0` across all 48 teams (every simulated tournament has exactly one champion).
- Edge case: with `σ = 0` for every team (degenerate, force-set in a test), the luck factor collapses and results converge to a pure-Poisson simulation; this is a useful regression target proving the luck factor is the only stochastic perturbation beyond Poisson sampling itself.
- Edge case: a JSON team name not present in `dim_team` raises with a clear "team not registered: <name>" error before any simulation runs.
- Integration scenario: re-running with the same seed yields byte-identical `probabilities.csv` — proves the rng is threaded correctly.

**Verification:**
- `python3 methodology/curated-poisson-luck/simulate.py --n 10000 --seed 42` writes `results/curated-poisson-luck/<today>/probabilities.csv` and `probabilities.json`.
- Stage probabilities are monotone non-increasing along the bracket per team: `p_r32 ≥ p_r16 ≥ p_qf ≥ p_semi ≥ p_final ≥ p_champion`. Any violation indicates a bracket-walker bug.

---

- [ ] **Unit 5: Register the model in `dim_model`**

**Goal:** Add the new model to the master `db/masters/models.csv` and a `MODEL.md` card so a clean DuckDB rebuild includes `curated-poisson-luck` in `curated.dim_model`.

**Requirements:** R6

**Dependencies:** Unit 3 (the `MODEL.md` references the methodology path and `predictions.csv` output location).

**Files:**
- Modify: `db/masters/models.csv` — add one row.
- Create: `results/curated-poisson-luck/MODEL.md` — model card.

**Approach:**
- New `models.csv` row: `curated-poisson-luck,Curated Poisson with Luck Factor,single-source,methodology/curated-poisson-luck/,results/curated-poisson-luck/,pending_backtest`.
- MODEL.md follows the existing template (see `results/poisson-goals/MODEL.md`): fields for approach, stack, data sources, training window, calibration, confidence, update cadence, output location, markets covered, known limitations, validation status, missing-player policy, stale-data policy, injury policy, market-usage boundary.
- Critically, the `Data sources` field lists `curated.fact_international_match`, `curated.fact_team_economics`, `curated.fact_team_fifa_ranking`, `curated.dim_team_recent_form`, `curated.dim_team_current` — explicit and curated-only.

**Patterns to follow:**
- `results/poisson-goals/MODEL.md` for the exact field set and ordering.

**Test scenarios:**
- Happy path: `tools/build_duckdb.py` (after a rebuild) loads the new row into `curated.dim_model`, and `SELECT model_id, model_name FROM curated.dim_model WHERE model_id = 'curated-poisson-luck'` returns exactly one row.
- Edge case: the `models.csv` row is the only file change needed; the master loader doesn't require any code edit because `tools/build_duckdb.py` already auto-derives `dim_model` from the CSV.

**Verification:**
- `tools/verify_duckdb.py` exits 0 after rebuild.
- `duckdb data/wc2026.duckdb -c "SELECT * FROM curated.dim_model WHERE model_id = 'curated-poisson-luck'"` returns the new row.

---

- [ ] **Unit 6: README and example queries**

**Goal:** Make the model self-documenting for the next contributor. A short README explaining how to run, what the luck factor means, and what calibration is pending; plus one or two example queries against `predictions.csv` shape.

**Requirements:** R6 (indirectly — the MODEL.md is the canonical card; the README is the developer-facing complement).

**Dependencies:** Units 3, 4, 5.

**Files:**
- Create: `methodology/curated-poisson-luck/README.md`
- Create: `db/queries/examples/curated_poisson_luck_per_team_features.sql` — runs the Unit 2 query directly so anyone can inspect the model inputs without touching Python.

**Approach:**
- README sections: Overview, How to Run, Inputs (curated tables consumed), Outputs, The Luck Factor (one paragraph + the truncated-Normal formula), Calibration Status, Known Limitations, Future Work.
- The example SQL file is a one-line wrapper: `-- Inspect the model inputs.` then the contents of `methodology/curated-poisson-luck/queries/team_model_features.sql`.

**Patterns to follow:**
- `results/README.md` for tone and brevity.
- Existing `db/queries/examples/*.sql` files for header docstring style.

**Test scenarios:**
Test expectation: none — documentation-only unit, no behavioral code change. (Verified by manual review and by Unit 5's `tools/verify_duckdb.py` rebuild proving nothing else regresses.)

**Verification:**
- README answers "how do I run this and what does the luck factor mean" in under 60 seconds of reading.
- The example query runs against `data/wc2026.duckdb` and returns 48 rows.

## System-Wide Impact

- **Interaction graph:** This model is read-only against the DuckDB. It does not write to any curated table. The only persistent change to the curated layer is one new row in `curated.dim_model` via `db/masters/models.csv`.
- **Error propagation:** The model script raises `RuntimeError` if `data/wc2026.duckdb` is missing or if the curated tables are empty (e.g., after a partial rebuild). The simulator raises if any tournament-JSON team name is unresolved in `dim_team`. No silent fallbacks beyond the documented λ / σ fallbacks for thin-sample teams.
- **State lifecycle risks:** `results/curated-poisson-luck/<today>/` is written non-destructively. Re-running on the same day overwrites that day's files (matches existing convention).
- **API surface parity:** `predictions.csv` shape matches every other model in `results/`. `probabilities.csv` shape matches `results/wc2026-sim/`. No new contracts.
- **Integration coverage:** Unit 5 plus a rebuild of `data/wc2026.duckdb` proves the `dim_model` registration round-trips. The integration test in Unit 4 (re-running with the same seed gives identical outputs) proves the rng plumbing.
- **Unchanged invariants:** `curated.*` schema is unchanged; all existing models (`elo-baseline`, `poisson-goals`, `ensemble-v2`, etc.) continue to read their own parquet/CSV inputs and remain untouched. `tools/build_duckdb.py` is unchanged. The four authoritative masters are unchanged except for one row added to `models.csv`.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `σ_team` is unstable for thin-sample teams (e.g., Haiti, n=16) — a single outlier match inflates σ and lets the luck factor produce unrealistic blowouts. | Floor σ at 0.4 (a sensible floor for international football). Cap λ_eff at a global ceiling (e.g., 4.5). Document both in `model.py` and in the MODEL.md `Known limitations`. |
| Tournament JSON contains names that don't resolve in `dim_team` (e.g., "Türkiye" vs "Turkey"). | Pre-flight name-resolution check at simulator startup raises with the full unresolved list. Fix by extending `dim_team.team_name` or adding an alias to a small bridge dict — both kept inside Unit 4. |
| `econ_multiplier` accidentally lets GDP dominate the model. | Hard cap on the multiplier (`[0.85, 1.15]`). Z-score clip at ±1. Decision 5 above. |
| `curated.fact_team_fifa_ranking` is a single snapshot — strength-of-schedule and FIFA prior reflect today, not the date of each historical match. | Acknowledged caveat (already documented on `dim_team_recent_form`). The model uses FIFA rank only as a prior for the current λ_team, not as a per-match retrospective weight, so the snapshot-only fact is fit-for-purpose here. |
| Tests in `tests/test_curated_poisson_luck_model.py` rely on a built `data/wc2026.duckdb`. | Mark the test module with a fixture that skips with a clear message if the DB is absent, so a clean clone doesn't trigger spurious failures before the user runs `tools/build_duckdb.py`. |

## Documentation / Operational Notes

- The MODEL.md card (Unit 5) is the canonical operator-facing doc.
- The README (Unit 6) is the contributor-facing doc.
- The model produces no Kalshi/Polymarket edge flags — it stops at `predictions.csv` / `probabilities.csv`. Edge comparison is the responsibility of the `07-edge-comparison` role (per `docs/agents/07-edge-comparison.md`) and is out of scope here.
- Until the WC2022 backtest lands, confidence is `medium` and the MODEL.md says so explicitly. The model is **not** safe to ensemble in yet, per the project's `wc2022_backtest_learnings.md` policy.

## Sources & References

- Curated schema contract: [`db/SCHEMA.md`](../../db/SCHEMA.md)
- Curated fact built in Unit 5 of: [`docs/plans/2026-05-15-001-feat-fact-international-match-plan.md`](2026-05-15-001-feat-fact-international-match-plan.md)
- Curated facts for economics and FIFA ranking: [`docs/plans/2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md`](2026-05-14-002-feat-fact-team-economics-and-fifa-ranking-plan.md)
- WC2026 bracket structure: `data/wc2026/tournament.json`
- Reference simulator: `tools/simulate_wc2026.py`
- Reference model card: `results/poisson-goals/MODEL.md`
- Ensemble policy: [`docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md`](../solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md)
- Model template: `methodology/_template/model.py`
