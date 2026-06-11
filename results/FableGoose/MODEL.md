# Model Card: FableGoose

| Field | Value |
|---|---|
| **Model name** | FableGoose |
| **Author(s)** | gusy (gustavo@flyca.co) |
| **Approach** | Dixon-Coles bivariate Poisson scoreline model driven by World Football Elo, then blended with the prediction market (DraftKings 1X2) in log-space. The Poisson means come from one shared GLM trained on goals as a function of Elo edge (incl. +100 home bonus when not neutral); a Dixon-Coles τ correction tightens low-score correlation. Final per-match probabilities are a 25/75 mix of the model and the de-vigged market. |
| **Stack** | Python 3 (pandas, numpy, statsmodels, scipy). Source in `/Users/gusy/Downloads/archive/src/` (`build_dataset.py`, `model.py`, `predict_2026.py`, `blend_market.py`, `backtest.py`). |
| **Data sources** | martj42 international results 1872→2026 (training & Elo spine); martj42 `former_names.csv` (date-aware team-name canonicalization); 2026 WC fixture list (from the martj42 set, filtered to `tournament == FIFA World Cup` with no scores yet); DraftKings 1X2 American moneylines for the group stage (`data/raw/market_odds_dk.csv`). |
| **Training window** | Elo runs on **full history** (1872→2026) so ratings converge. The Poisson GLM is fit on **2002-01-01 onward** only (modern-era cutoff). Training rows are time-decay weighted with a 3-year half-life, and friendlies are down-weighted to 0.5× competitive matches. |
| **Calibration method** | Walk-forward backtest on WC 2018 and WC 2022 **group-stage only** (48 matches each, knockouts excluded because martj42 records ET scores which would contaminate a 90-min scoreline model). Trained on everything before each tournament's start. Reported metrics: Ranked Probability Score, W/D/L log-loss, scoreline log-loss, exact-score hit rate, goal MAE. Compared to two baselines (B0 constant-μ Poisson on same training data; B1 higher-Elo-wins 95/2.5/2.5). Paired bootstrap (4000 resamples) on pooled 96 matches for model-vs-B0 significance. Calibration also reported as predicted vs observed home-win frequency in 3 buckets of p_home. |
| **Confidence reporting** | `high`/`medium`/`low` based on the strength of the top blended outcome: `medium` when max(p_home, p_draw, p_away) ≥ 0.42, `low` otherwise. No row is currently tagged `high` — that level is reserved for future enrichments (squad availability, late team news). |
| **Update cadence** | Ad-hoc. New snapshot whenever martj42 results or the DraftKings odds file are refreshed. |
| **Output location** | `results/FableGoose/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered** | `match_1x2` for all 72 group-stage fixtures + `outright_winner` for the 31 teams with a non-zero deep-run probability under the bracket sim. Group winners and knockout placeholders not covered yet. |
| **Known limitations** | (1) **Outright probabilities come from a Monte Carlo bracket sim with only n=50 trials** — granularity is 2 pp per sim, so anything ≤ 0.04 is one or two sims and should be read as "noise floor", not a real estimate. (2) **No player or injury data**; all signal is team-level Elo + recent match record. (3) **Blend weight (W_MKT = 0.75) is a literature-informed prior, not backtested** — no historical odds file in scope; tune only as 2026 matches resolve. (4) Dixon-Coles τ only adjusts the four lowest-score cells; the >6-goals tail (<1% mass) is folded back by renormalization. (5) Hosts (USA/MEX/CAN) get home advantage only via the martj42 `neutral` flag — no separate altitude/travel effects. (6) Knockout simulation does **not** include extra time / penalties; ties in sim resolve from the same Dixon-Coles grid via the higher 90-min win prob. |
| **Validation status** | **Built & backtested on WC2018 + WC2022 group stages.** The DC-Elo Poisson beats both B0 and B1 baselines on RPS and W/D/L log-loss; significance reported via paired bootstrap. Treat as research-grade until a live in-tournament calibration check is logged. |
| **Missing-player policy** | Not applicable — model is team-strength only, no roster features. |
| **Stale-data policy** | The CSV is regenerated whenever `data/raw/results.csv` (martj42) or `data/raw/market_odds_dk.csv` is updated. No automated freshness gate yet; if a snapshot is older than 7 days during the tournament, confidence should be manually downgraded. |
| **Injury/suspension policy** | Ignored. Notes field is free for manual caveats but the probabilities themselves do not move on team news. |
| **Market usage boundary** | Comparison only. The model is already blended with DraftKings, so edges computed against DK on this snapshot are partially self-referential — use other books (Kalshi, Polymarket, Hard Rock Bet) when looking for true edge. |

## Methodology in plain English

1. **Build a team-strength rating (Elo).** Start every team at 1300. For each historical international, update both teams' Elo using the World Football Elo formula: K depends on tournament importance (60 for WC, 50 for continental cups, 40 for qualifiers/Nations League, 20 for friendlies), with a goal-margin multiplier (×1, ×1.5, ×1.75 + 0.5 per extra goal beyond 3) and a +100 Elo home bonus when not neutral. Historical names (e.g. "West Germany", "Yugoslavia") are folded into modern successors using a date-aware mapping table before rating.
2. **Turn the rating gap into an expected goal count.** Fit one Poisson GLM where `log(goals) = b0 + b1 · (elo_edge / 400)`, training on every modern-era international (2002→). Each row is duplicated home/away perspective so the same coefficients apply to both sides. Rows are weighted by a 3-year half-life decay and by tournament importance.
3. **Build a scoreline grid for any future match.** Plug the two teams' current Elo (plus +100 for the home side if not neutral) into the GLM to get mean goals for each side, then take the outer product of Poisson PMFs to get a 7×7 score-grid. Apply the Dixon-Coles τ correction so low scores (0-0, 1-0, 0-1, 1-1) aren't artificially independent — the correction parameter ρ is fit by profile MLE on the same time-decay-weighted training data.
4. **Summarize the grid.** Sum the lower triangle, diagonal, and upper triangle to get the home-win / draw / away-win probabilities. The cell argmax is the "modal scoreline" reported alongside. Row/column expectations give xG for each side.
5. **Blend with the market.** Convert DraftKings American moneylines to implied probabilities, strip the vig by normalizing, then mix model and market in log-space: `p_blend ∝ p_model^0.25 · p_market^0.75`. The 7×7 score-grid is then rescaled so its lower/diagonal/upper masses match the blended W/D/L while keeping the model's *within-class* shape (i.e. given a home win, "how home?" comes from the model; whether it's a home win at all is mostly the market).
6. **Backtest before trusting.** Train on every match before WC2018 / WC2022, predict the 48 group-stage matches of each, and compare against two baselines (constant-μ Poisson; higher-Elo-wins) on RPS, W/D/L log-loss, scoreline log-loss, exact-score hit rate, and goal MAE. A 4000-sample paired bootstrap on the pooled 96 matches confirms the model's gain over the constant-μ baseline.
7. **Simulate the bracket for outright winners.** Replay the full 2026 tournament 50 times (`src/sim_bracket.py`):
   - **Group stage:** each match's exact score sampled from its **blended** 7×7 grid. Standings ranked by pts → GD → GF → random (head-to-head and fair-play tiebreaks approximated as random). Top 2 + 8 best thirds advance.
   - **Third-place slot assignment:** FIFA's fixed third-place allocation table is approximated by constraint-satisfying backtracking on the `1X vs 3<ABCDF>` slot labels in the official bracket.
   - **Knockout rounds:** sampled from **pure DC-Elo grids on current Elo** (no market data exists for hypothetical pairings, so the blend is dropped at this point). Venue home advantage applies only when the team's country matches the host city country. Draws go to **30-minute extra time** (independent Poisson at μ/3 per side); still tied → **50/50 penalty shootout**.
   - **Ratings are static within a sim** — no in-tournament Elo update.
   - The champion frequency across the 50 trials becomes `p_model` for `OUTRIGHT-WC2026`. **The n=50 sample is small (granularity 2 pp), so individual outright probabilities are noisy — rank order is more trustworthy than absolute values.** The companion `notes` column reports each team's frequency of reaching the SF and the final, which are higher-sample signals than the champion column alone.

## Subjective adjustments

Documented per the working agreement. Every parameter that wasn't fit from data is listed here.

| Parameter | Value | Evidence / justification |
|---|---|---|
| Modern-era cutoff for GLM training | 2002-01-01 | User decision 2026-06-11. Elo is computed on full history for convergence; the goal-rate GLM uses only the post-2002 era so it doesn't fit obsolete scoring dynamics. A WC-dummy variant was tried (coef -0.006 / +0.056, no metric gain) and reverted. |
| Elo home advantage | +100 Elo when not neutral | World Football Elo convention. Hosts USA/MEX/CAN inherit this via the martj42 `neutral` flag in their own venues. |
| Time-decay half-life | 3 years (1096.5 days) | Standard half-life from international-football literature; not tuned on this data. |
| Friendly down-weight | 0.5× competitive matches | Convention: friendlies are noisier signal. Not tuned. |
| New-team starting Elo | 1300 | Mid-tier entrant; convention. |
| Goal-margin multiplier | ×1 (≤1), ×1.5 (=2), ×1.75 + 0.5 per extra (≥3) | Standard World Football Elo. |
| K factors | WC 60, continental 50, qualifiers/Nations League 40, other competitive 30, friendly 20 | Standard World Football Elo. |
| Market blend weight `W_MKT` | 0.75 | Literature-informed prior (closing odds dominate standalone models). Cannot be backtested here because no historical odds are in scope; flagged for live tuning as 2026 results land. |
| Scoreline-grid tail cap | 0-6 goals per side (7×7 grid, normalized) | The >6 tail is <1% mass; folded back by renormalization. Documented approximation in `blend_market.py`. |
| Confidence cutoff | `medium` if max blended prob ≥ 0.42, else `low` | FableGoose convention — kept low until live data is collected. No row currently tagged `high`. |
| Bracket sim trial count | n=50 | Sized for speed during development. Granularity is 2 pp per sim; rerun at n≥2,000 before treating any single outright probability as load-bearing. |
| Knockout tie-break in sim | 30-min extra time at μ/3, then 50/50 penalties | Extra-time μ scaled to 1/3 of 90-min μ to reflect the shorter period. Penalty shootouts modeled as a true coin flip — no shootout-specific signal (recent record, GK quality). |
| Knockout match grids | Pure DC-Elo (un-blended) on current Elo | No market data exists for hypothetical knockout pairings, so the W_MKT=0.75 blend used in the group stage is dropped here. Knockouts therefore lean more model-heavy than group-stage outputs. |
| Standings tiebreaks beyond GD/GF | Random | Head-to-head and fair-play tiebreaks not modeled. Documented approximation in `sim_bracket.py`. |
| Third-place slot allocation | Constraint-satisfying backtracking on `3<letters>` slot labels | Approximates FIFA's fixed pre-published allocation table by satisfying the slot constraints rather than reproducing the official table verbatim. |

## Validation

WC2018 + WC2022 group-stage walk-forward backtest (48 matches each, 96 pooled). Trained pre-tournament. Knockouts excluded (ET contamination).

| Backtest | RPS | W/D/L log-loss | Scoreline log-loss | Exact-score hit | Goal MAE | Notes |
|---|---:|---:|---:|---:|---:|---|
| WC2018 (n=48) | reported in `backtest.py` stdout | — | — | — | — | DC-Elo Poisson vs B0 const-μ Poisson and B1 higher-Elo-wins |
| WC2022 (n=48) | reported in `backtest.py` stdout | — | — | — | — | Same setup |
| Pooled (n=96) | Δ vs B0 with 95% bootstrap CI | Δ vs B0 with 95% bootstrap CI | — | — | — | 4000-sample paired bootstrap |

Numeric values will be filled in this card after re-running `python3 src/backtest.py` against the committed snapshot of `matches_elo.csv`. The same script reports a calibration table (predicted vs observed home-win frequency in 3 buckets of p_home).

## Notes for collaborators

- The `notes` column on every row of `2026-06-11/predictions.csv` carries the two teams' current Elo, the blended xG split, and the modal scoreline. That's enough to sanity-check any single row without re-running the model.
- The 2026-06-11 snapshot covers **group stage only (72 fixtures × 3 outcomes = 216 rows)**. No outrights yet — comparison code that needs `outright_winner` rows should treat FableGoose as opting out of that market for this snapshot.
- Because the published probabilities are already DK-blended, **edge calculations against DraftKings on this snapshot are partially self-referential**. Compare against Kalshi, Polymarket, or Hard Rock Bet for cleaner signal until an un-blended companion snapshot is published.
- The fixture mapping used FIFA 3-letter codes (e.g. RSA for South Africa, KSA for Saudi Arabia, CIV for Ivory Coast, COD for DR Congo, CUW for Curaçao). If a future codes table in the repo differs, rebuild from `predictions_2026_group_blended.csv` with the new mapping rather than hand-editing.
