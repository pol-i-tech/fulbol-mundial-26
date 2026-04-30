# DEVELOPMENT.md

Project guide for contributors — human or AI (Claude Code, Cursor, Codex, Gemini, etc.).

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

### Prediction integrity checks
- Probabilities for mutually exclusive outcomes sum to ≥0.99 and ≤1.01 per `(match_id, market_type)`
- All team codes are 3-letter FIFA format — no free-form country names
- No `p_model` values outside [0, 1]
- `as_of_date` matches the folder name
- `notes` field describes model reasoning only — never market comparisons or edge flags (edge detection is the comparison layer's job)

### What reviewers check
- Is `methodology/` present and runnable?
- Are all subjective adjustments listed in MODEL.md with justification?
- Does the model's approach match what `MODEL.md` claims?
- Is the backtest walk-forward (no future data leakage)?
- Do outright/group markets sum to 1.0 across all outcomes?

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
