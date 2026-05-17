# DEVELOPMENT.md

Contribution workflow + model guardrails. For project shape (directory map, data flow, tech stack), see [`ARCHITECTURE.md`](./ARCHITECTURE.md). For the role catalog, see [`AGENTS.md`](./AGENTS.md).

## How to contribute

Pick a role from [`AGENTS.md`](./AGENTS.md) (data engineering, data coverage, data cleaning, modeling, or validation), then follow the workflow below. The as-is structure (directory map, where outputs land, how the pipeline runs) is in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Current Priority Stack

Work should stay inside this stack unless a lead explicitly changes scope:

1. **Guardrails and validation** — keep prediction snapshots trustworthy and reproducible.
2. **Player-data coverage** — close missing-player and stale-player gaps before adding model complexity.
3. **Model consolidation** — keep the single canonical model (`methodology/wc2026-predictor/`) reproducible; any parallel model lands under `methodology/<name>/` against the same `db/SCHEMA.md` contract.
4. **Only then:** tournament simulation features, dashboards, notebooks, new market types.

> Market normalization, devig, and edge-comparison work are out of scope for this repo. The single-model output is the deliverable; market comparison lives elsewhere.

Deferred until after the core pipeline is stable:

- New UI/dashboard work beyond the Graphene viz already wired to `data/wc2026.duckdb`.
- Live bet execution or account integrations.
- LLM/agent-driven scraping.
- Re-attempting FBref.

## Contribution Workflow

**Main is protected.** No one pushes directly to `main` — not humans, not agents.

### Branch naming

```
<your-name>/feature-description     # e.g. luis/add-xg-poisson-model
<your-name>/fix-description         # e.g. ana/fix-name-resolver
<your-name>/data-description        # e.g. jorge/pull-understat-ucl
```

### Workflow

1. Branch off `main`: `git checkout -b <your-name>/<description>`
2. Do your work. Commit often with descriptive messages.
3. Push your branch: `git push -u origin <your-name>/<description>`
4. Open a PR on GitHub — the PR template will guide you through the checklist.
5. Request review from at least one other contributor.
6. **Do not merge your own PR** — wait for an approved review.
7. Squash-merge into `main` once approved.

### Review rules

- Every PR requires **1 approving review** before merge.
- Stale reviews are dismissed automatically when new commits are pushed — re-approval is required.
- PRs touching `results/` or `tools/` are owned by `@pol-i-tech/leads` (auto-requested).
- Force-pushing to `main` is blocked at the GitHub level.

## Model Guardrails

Any new or updated model must satisfy these before merging:

### Required artifacts

Every model needs three things committed together:

```
methodology/<model-name>/          ← reproducible code or notebook
    README.md                      ← how to run it end-to-end
    <model>.py / <model>.ipynb     ← the actual methodology
    requirements.txt               ← dependencies (if any beyond project base)

results/<model-name>/
    MODEL.md                       ← model card
    <YYYY-MM-DD>/
        predictions.csv            ← 8-column output
```

The `methodology/` folder is **required**. A predictions CSV with no reproducible code will not be merged. The methodology must be runnable by any contributor from a clean clone.

### Reproducibility standard

- Running the methodology code must regenerate `predictions.csv` deterministically (set random seeds explicitly).
- All input data must come from `data/wc2026.duckdb` (preferred) or `data/derived/` or documented public sources — no manual data entry.
- If the model uses a spreadsheet, export the computation logic as a script or attach the sheet to `methodology/<model-name>/`.
- Document the exact command to reproduce: `python3 methodology/<model-name>/model.py` or equivalent.
- Run `python3 tools/validate_predictions.py results/<model-name>/<YYYY-MM-DD>/predictions.csv` before submitting.

### Subjectivity and bias policy

Models will inevitably use judgment calls (team tiers, importance weights, adjustments). This is acceptable **only when explicitly documented**:

- Every manually set parameter or override must be listed in `MODEL.md` under a **"Subjective adjustments"** section.
- Each entry must state: what the adjustment is, what value it takes, and the evidence or reasoning behind it.
- **Adjustments must not be changed between snapshots without a corresponding backtest showing improvement** — this prevents post-hoc fitting to known results.
- Reviewer responsibility: flag any undocumented parameter that could encode personal bias (e.g., boosting a favourite national team without statistical basis).

Examples of adjustments that require documentation:

- Team tier classifications.
- Confederation bonuses/penalties.
- Player or team "surprise" factors.
- Draw probability caps.
- Match importance weights that differ from project defaults.

**Project-wide priors live in `db/masters/*.csv`** (e.g., `db/masters/tournament_tier_weights.csv`). Do not hardcode tier weights or importance dicts in model code; join `curated.dim_tournament_tier_weight` instead.

### Statistical validation bar

- Backtest against at least one held-out tournament (WC2022, Euro2024, or Copa2024).
- Report **log-loss**, **Brier score**, and **accuracy** in `MODEL.md`.
- Log-loss must beat a naive uniform prior (log-loss < 1.099 for 3-outcome markets).
- Walk-forward only — no in-sample validation.
- Do not promote a model from research to canonical (`wc2026-predictor`'s seat) unless it also beats the incumbent on a held-out tournament.

### Model limitations that must be stated

Every `MODEL.md` must explicitly cover:

- **Missing-player policy:** how the model treats players absent from club/national xG data.
- **Stale-data policy:** how old player or team data can be before the model refuses to update or downgrades confidence.
- **Injury/suspension policy:** whether the model ignores, manually adjusts, or programmatically ingests availability.
- **Squad uncertainty:** whether probabilities assume likely squads, confirmed squads, or full national pools.
- **Known blind spots:** tactical changes, new managers, late squad announcements, home-continent effects, travel/altitude, or any omitted factors.

### Prediction integrity checks

- Probabilities for mutually exclusive outcomes sum to ≥0.99 and ≤1.01 per `(match_id, market_type)`.
- All team codes are 3-letter FIFA format — no free-form country names.
- No `p_model` values outside [0, 1].
- `as_of_date` matches the folder name.
- `notes` field describes model reasoning only.
- Date-snapshot files must have exactly the eight shared columns. Backtest diagnostic files can include actuals, but should be named `predictions_vs_actual.csv` or live under `results/comparisons/`.

### What reviewers check

- Is `methodology/` present and runnable?
- Are all subjective adjustments listed in MODEL.md with justification?
- Does the model's approach match what `MODEL.md` claims?
- Is the backtest walk-forward (no future data leakage)?
- Do outright/group markets sum to 1.0 across all outcomes?
- Does `tools/validate_predictions.py --all` pass?

## Prediction Output Schema

Every model writes `results/<model-name>/<YYYY-MM-DD>/predictions.csv` with exactly these 8 columns:

| Column | Example |
|---|---|
| `as_of_date` | `2026-05-16` |
| `match_id` | `WC26-MEX-RSA-2026-06-11` (group), `WC26-R16-08` (slot-based knockout), or `WC26-R32-FRA-GER` (pair-based knockout emitted by the MC sim) |
| `market_type` | `match_1x2` / `outright_winner` / `group_winner` / `team_advances` / `totals` / `btts` |
| `outcome` | `home`/`draw`/`away` for 1X2; 3-letter FIFA code for outrights; player name for top scorer |
| `p_model` | float [0,1]; rows sum to ~1.0 per (match_id, market_type) for mutually exclusive markets |
| `confidence` | `high`/`medium`/`low` or float 0–1 — pick one convention, document in MODEL.md |
| `model_version` | git SHA, semver, or date string |
| `notes` | optional free-form context |

Team codes: 3-letter FIFA codes throughout (ARG, FRA, MEX, RSA…). Canonical team metadata lives in `curated.dim_team`.

## Key Constraints

- **FBref is hard-blocked by Cloudflare** — both `soccerdata` wrapper and direct requests fail. Do not attempt. Use `martj42/international_results` (GitHub raw CSV) for form data instead.
- **`squad_xg_ratings.parquet`** is built from historical tournament/event data, not necessarily final WC2026 squads. Confirmed-squad ingestion is on the roadmap; see `tools/pull_wc2026_final_squads.py`.
- **No hardcoded modeling weights.** Tournament tier weights and project-wide priors live in `db/masters/*.csv` → `curated.dim_*`, never as CASE literals in model code.
- **Model data lives in DuckDB.** The canonical model (`methodology/wc2026-predictor/`) reads only from `curated.*` in `data/wc2026.duckdb`. New models should follow the same discipline.

## Adding a new model

Copy `methodology/_template/` to a new folder, follow the guardrails above, and submit a PR. The active reference implementation is `methodology/wc2026-predictor/` — read its code and `results/wc2026-predictor/MODEL.md` for the shape a contribution should take.

## Player data gap plan

Player coverage is a known gap with an active roadmap at [`docs/agents/data-gaps-roadmap.md`](./docs/agents/data-gaps-roadmap.md). Highlights:

- Coverage per nation is measured and reported in `data/derived/player_coverage_report.csv`.
- Confirmed WC2026 squads are not yet integrated into the model pipeline.
- Manual name overrides should live in a documented exceptions file rather than buried inside fuzzy matching code.

## Environment Variables

Currently no required env vars — the canonical model reads only local files. Future:

```
ODDS_API_KEY=<reserved for any future The Odds API integration>
```
