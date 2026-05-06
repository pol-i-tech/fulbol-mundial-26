# DEVELOPMENT.md

Project guide for contributors — human or AI (Claude Code, Cursor, Codex, Gemini, etc.).

## Ways to Contribute

**You don't need to build a full pipeline to contribute.** Committed seed data is available in `data/derived/` the moment you clone the repo. Pick the track that fits your skills:

---

### Track A — Model contributor
*You have a prediction approach and want to submit it.*

The shared data is ready to use:
```
data/derived/squad_xg_ratings.parquet     # player xG ratings for WC2026 squads
data/derived/statsbomb_player_xg.parquet  # player xG from WC2022, Euro2024, Copa2024
data/derived/statsbomb_team_xg.parquet    # team-level xG per match
data/derived/understat_player_xg.parquet  # club-level player xG (current season)
data/derived/team_attack_ratings.parquet  # team attack ratings
data/derived/kalshi_snapshot_<date>.csv   # latest Kalshi market prices
data/derived/polymarket_snapshot_<date>.csv  # latest Polymarket prices
```

Your model reads from `data/derived/`, runs in `methodology/<your-model>/`, writes to `results/<your-model>/<date>/predictions.csv`. That's it — no data pipeline required.

See [Adding a New Model](#adding-a-new-model) for the full checklist.

---

### Track B — Data contributor
*You want to add a new data source or enrich existing data.*

Good candidates: UCL/Champions League event data, Nations League xG, updated Elo ratings, WC2026 injury/suspension feeds, squad depth charts.

- New pull scripts go in `tools/`
- Raw data goes in `data/raw/<source>/<YYYY-MM-DD>/` (immutable, gitignored)
- Derived outputs go in `data/derived/` as `.parquet` (and `.csv` if human-readable)
- Scripts must be idempotent — safe to re-run without duplicating data
- Document the source, update cadence, and any rate limits in the script header

Data additions automatically become available to all model contributors on next pull.

---

### Track C — Analysis contributor
*You want to run backtests, comparisons, or edge analysis.*

- Backtest scripts go in the repo root or `tools/` (follow `wc2022_xg_backtest.py` as a pattern)
- Output goes in `results/comparisons/` or `results/<your-analysis>/`
- Analysis must be reproducible (a script, not a notebook with manual steps)
- Share findings as a PR with a summary in the PR description — this is how we build collective knowledge

---

### Track D — Documentation / tooling contributor
*You want to improve the pipeline, fix bugs, or update docs.*

- All changes go through a PR
- `DEVELOPMENT.md`, `AGENTS.md`, and `CLAUDE.md` are the canonical docs — keep them in sync
- `tools/weekly_pull.py` is the main orchestration script — changes here require extra review

---

## Current Priority Stack

Work should stay inside this stack unless a lead explicitly changes scope:

1. **Guardrails and validation** — keep prediction snapshots trustworthy and reproducible.
2. **Player-data coverage** — close missing-player and stale-player gaps before adding model complexity.
3. **Market normalization** — devig, volume filters, and Pinnacle comparison must match the documented betting rule.
4. **Model consolidation** — move orphan model logic into `methodology/<model-name>/` and document how to regenerate each snapshot.
5. **Only then:** tournament simulation, dashboards, notebooks, or new market types.

Deferred until after the core pipeline is stable:

- New UI/dashboard work.
- Additional bookmakers beyond Kalshi, Polymarket, and Pinnacle/Hard Rock via The Odds API.
- Live bet execution or account integrations.
- LLM/agent-driven scraping.
- Re-attempting FBref.

---

## Contribution Workflow

**Main is protected.** No one pushes directly to `main` — not humans, not agents.

### Branch naming
```
<your-name>/feature-description     # e.g. luis/add-xg-poisson-model
<your-name>/fix-description         # e.g. ana/fix-kalshi-devig
<your-name>/data-description        # e.g. jorge/pull-understat-ucl
```

### Workflow
1. Branch off `main`: `git checkout -b <your-name>/<description>`
2. Do your work. Commit often with descriptive messages.
3. Push your branch: `git push -u origin <your-name>/<description>`
4. Open a PR on GitHub — the PR template will guide you through the checklist
5. Request review from at least one other contributor
6. **Do not merge your own PR** — wait for an approved review
7. Squash-merge into `main` once approved

### Review rules
- Every PR requires **1 approving review** before merge
- Stale reviews are dismissed automatically when new commits are pushed — re-approval is required
- PRs touching `results/`, `compound-model/`, or `tools/` are owned by `@pol-i-tech/leads` (auto-requested)
- Force-pushing to `main` is blocked at the GitHub level

---

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
- Running the methodology code must regenerate `predictions.csv` deterministically (set random seeds explicitly)
- All input data must come from `data/derived/` or documented public sources — no manual data entry
- If the model uses a spreadsheet, export the computation logic as a script or attach the sheet to `methodology/<model-name>/`
- Document the exact command to reproduce: `python3 methodology/<model-name>/model.py` or equivalent
- Run `python3 tools/validate_predictions.py results/<model-name>/<YYYY-MM-DD>/predictions.csv` before submitting

### Subjectivity and bias policy

Models will inevitably use judgment calls (team tiers, importance weights, adjustments). This is acceptable **only when explicitly documented**:

- Every manually set parameter or override must be listed in `MODEL.md` under a **"Subjective adjustments"** section
- Each entry must state: what the adjustment is, what value it takes, and the evidence or reasoning behind it
- **Adjustments must not be changed between snapshots without a corresponding backtest showing improvement** — this prevents post-hoc fitting to known results
- Reviewer responsibility: flag any undocumented parameter that could encode personal bias (e.g., boosting a favourite national team without statistical basis)

Examples of adjustments that require documentation:
- Team tier classifications
- Confederation bonuses/penalties
- Player or team "surprise" factors
- Draw probability caps
- Match importance weights that differ from project defaults

### Statistical validation bar
- Backtest against at least one held-out tournament (WC2022, Euro2024, or Copa2024)
- Report **log-loss**, **Brier score**, and **accuracy** in `MODEL.md`
- Log-loss must beat a naive uniform prior (log-loss < 1.099 for 3-outcome markets)
- If claiming edge vs market: show calibration plot or ECE score
- Walk-forward only — no in-sample validation
- Do not promote a model from research to actionable unless it also beats or plausibly complements the existing ensemble on a held-out tournament.

### Model limitations that must be stated

Every `MODEL.md` must explicitly cover:

- **Missing-player policy:** how the model treats players absent from club/national xG data.
- **Stale-data policy:** how old player or team data can be before the model refuses to update or downgrades confidence.
- **Injury/suspension policy:** whether the model ignores, manually adjusts, or programmatically ingests availability.
- **Squad uncertainty:** whether probabilities assume likely squads, confirmed squads, or full national pools.
- **Market usage boundary:** whether model outputs are for comparison only or eligible for edge calculation.
- **Known blind spots:** tactical changes, new managers, late squad announcements, home-continent effects, travel/altitude, or any omitted factors.

### Prediction integrity checks
- Probabilities for mutually exclusive outcomes sum to ≥0.99 and ≤1.01 per `(match_id, market_type)`
- All team codes are 3-letter FIFA format — no free-form country names
- No `p_model` values outside [0, 1]
- `as_of_date` matches the folder name
- `notes` field describes model reasoning only — never market comparisons or edge flags (edge detection is the comparison layer's job)
- Date-snapshot files must have exactly the eight shared columns. Backtest diagnostic files can include actuals, but should be named `predictions_vs_actual.csv` or live under `results/comparisons/`.

### What reviewers check
- Is `methodology/` present and runnable?
- Are all subjective adjustments listed in MODEL.md with justification?
- Does the model's approach match what `MODEL.md` claims?
- Is the backtest walk-forward (no future data leakage)?
- Do outright/group markets sum to 1.0 across all outcomes?
- Does `tools/validate_predictions.py --all` pass?

---

## Project Purpose

Multi-contributor WC 2026 prediction workbench. Each contributor submits predictions in a standard 8-column CSV format. The comparison framework (`tools/weekly_pull.py`) joins all model predictions against devigged betting market prices (Kalshi, Polymarket, Pinnacle) to surface positive-edge opportunities using the Golden Zone rule.

## Running the Pipeline

### Weekly refresh (data + markets + Elo baseline + comparison)
```bash
python3 tools/weekly_pull.py              # uses today's date
python3 tools/weekly_pull.py 2026-06-15   # specific date
```
Outputs: raw JSON snapshots in `data/raw/`, normalized CSVs in `data/derived/`, Elo predictions in `results/elo-baseline/<date>/`, comparison table in `results/comparisons/<date>/`.

### Data pull scripts (run in order when building from scratch)
```bash
python3 tools/pull_statsbomb.py           # ~5-10 min; caches per-match JSON
python3 tools/pull_wc2026_squads.py       # Wikipedia squad scraper; caches HTML
python3 tools/pull_understat_players.py   # club-level player xG
python3 tools/aggregate_statsbomb_players.py   # depends on pull_statsbomb output
python3 tools/build_squad_xg_ratings.py  # depends on aggregate + understat output
```

### Backtest
```bash
python3 wc2022_xg_backtest.py             # walk-forward WC 2022; ~30 sec
```
Outputs predictions to `results/poisson-xg/wc2022-backtest/` and `results/ensemble-v2/wc2022-backtest/`.

## Architecture

### Data flow
```
Raw sources → data/raw/<source>/<YYYY-MM-DD>/   (immutable, gitignored)
            → data/derived/*.parquet / *.csv     (normalized, gitignored)
            → results/<model>/<YYYY-MM-DD>/predictions.csv  (8-column schema)
            → results/comparisons/<date>/comparison.csv     (all models + market edges)
```

### Model pipeline (compound-model)
1. `pull_statsbomb.py` → `data/derived/statsbomb_player_xg.parquet`
2. `aggregate_statsbomb_players.py` → `data/derived/sb_player_summary.parquet`
3. `pull_understat_players.py` → `data/derived/understat_player_xg.parquet`
4. `build_squad_xg_ratings.py` → `data/derived/squad_xg_ratings.parquet` (blended_xg90 = 0.4×national + 0.6×club), `data/derived/team_attack_ratings.parquet`
5. Dixon-Coles fit on 7.9k matches (2018–present, time-decayed `xi` ∈ [0.001, 0.003])
6. 10k Monte Carlo simulation of 2026 bracket (12 groups → best-8-thirds → R32 onward)
7. `weekly_pull.py` joins predictions against Kalshi/Polymarket/Pinnacle

### Market normalization
- Devig method: **Power** for 1X2 markets, **Shin** for outrights/group winners
- Kalshi reads are unauthenticated GETs (RSA signing only needed for trading)
- Kalshi group-winner markets include phantom teams at 1–8%: inner-join against known fixtures before devigging
- All market prices stored as implied probability [0, 1]
- Raw quoted prices are informational only. Do not label a row actionable until devigging and liquidity filters have run.

### Betting rule
- **Golden Zone**: all 3 base models (Elo, Form, Poisson) agree on the same favourite
- **Edge threshold**: model_p > devigged_market_p by ≥3% AND > Pinnacle by ≥1.5%
- **Kelly sizing**: half-Kelly, capped at 2% bankroll. Skip 3-way model splits.
- WC 2022 backtest result: +5.2% ROI on Golden Zone games. Ensemble-v2 log-loss 1.054 (Pinnacle baseline: 1.000).

### Match importance weights (recency decay)
`WC=1.0, Euro/Copa=0.9, WCQ=0.7, Nations League=0.6, friendly=0.35`

## Prediction Output Schema

Every model writes `results/<model-name>/<YYYY-MM-DD>/predictions.csv` with exactly these 8 columns:

| Column | Example |
|---|---|
| `as_of_date` | `2026-04-28` |
| `match_id` | `WC26-MEX-RSA-2026-06-11` (group) or `WC26-R16-08` (knockout) |
| `market_type` | `match_1x2` / `outright_winner` / `group_winner` / `team_advances` / `totals` / `btts` |
| `outcome` | `home`/`draw`/`away` for 1X2; 3-letter FIFA code for outrights; player name for top scorer |
| `p_model` | float [0,1]; rows sum to ~1.0 per (match_id, market_type) for mutually exclusive markets |
| `confidence` | `high`/`medium`/`low` or float 0–1 — pick one convention, document in MODEL.md |
| `model_version` | git SHA, semver, or date string |
| `notes` | optional free-form context |

Team codes: 3-letter FIFA codes throughout (ARG, FRA, MEX, RSA…). The `NAME_TO_FIFA3` and `ISO2_TO_FIFA3` dicts live in `tools/weekly_pull.py`.

## Key Constraints

- **FBref is hard-blocked by Cloudflare** — both `soccerdata` wrapper and direct requests fail. Do not attempt. Use `martj42/international_results` (GitHub raw CSV) for form data instead.
- **`squad_xg_ratings.parquet` exists but is not yet wired into the compound model** — this is the highest-priority unwired feature.
- **Kalshi outright/group markets have zero trading volume** (operator-priced pre-tournament) — always filter on `min_volume` before flagging edge.
- **KXWCGAME ticker format**: `KXWCGAME-26<MON><DD><HOME3><AWAY3>`. Regex: `KXWCGAME-26([A-Z]{3})(\d{2})([A-Z]{3})([A-Z]{3})`. Already implemented in `normalize_kalshi()`.

## Player Data Gap Plan

The current player pipeline has useful but incomplete coverage:

- `sb_player_summary.parquet`: national-team event data from StatsBomb tournaments.
- `understat_player_xg_raw.parquet`: club xG, mainly top European leagues.
- `squad_xg_ratings.parquet`: fuzzy join of the two sources.
- `team_attack_ratings.parquet`: team-level aggregation of top attacking/pressing signals.

Before improving model complexity, close these gaps:

1. **Measure coverage per nation.** For every team, report squad players, club-xG matches, national-xG minutes, and unmatched names.
2. **Create an exceptions file.** Store manual name mappings in `data/derived/player_name_overrides.csv` or `tools/player_name_overrides.py`; do not bury overrides inside fuzzy matching code.
3. **Add missing-player defaults.** Missing club xG should not silently equal national xG. Use a documented fallback by position and nation tier, and downgrade confidence.
4. **Separate likely squad from historical player pool.** `squad_xg_ratings.parquet` currently reflects players present in historical tournament/event data, not necessarily final WC2026 squads.
5. **Add freshness checks.** If club data is older than the current season or a player has low minutes, lower that player's weight.
6. **Backtest any new player signal.** Do not wire lineup/player xG into the production comparison unless WC2022/Euro2024/Copa2024 validation improves calibration or explains a documented blind spot.

The full player acquisition strategy is in `docs/plans/2026-05-06-world-cup-player-data-acquisition-strategy.md`.

## Adding a New Model

```bash
# 1. Copy templates
cp -r methodology/_template methodology/<your-model-name>
mkdir -p results/<your-model-name>
cp results/_template/MODEL.md results/<your-model-name>/
```

2. Build your methodology in `methodology/<your-model-name>/` — code, notebook, or documented spreadsheet export
3. Fill in `results/<your-model-name>/MODEL.md` — including the **"Subjective adjustments"** section
4. Run your model and write predictions to `results/<your-model-name>/<YYYY-MM-DD>/predictions.csv`
5. Run the backtest against WC2022/Euro2024/Copa2024 and record log-loss + accuracy in MODEL.md
6. Add a row to the root `README.md` model table
7. Do not modify another contributor's `results/` or `methodology/` folder

## Environment Variables

Currently no required env vars — all market API reads are unauthenticated. Future:
```
ODDS_API_KEY=<free-tier key for The Odds API>
KALSHI_API_KEY_ID=<only needed for order placement, not reads>
KALSHI_PRIVATE_KEY_PATH=<only needed for order placement>
```
