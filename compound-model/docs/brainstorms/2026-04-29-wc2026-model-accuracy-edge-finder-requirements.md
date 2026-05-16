---
title: "WC 2026 Model Accuracy & Edge Finder — Improvement Plan"
type: requirements
status: active
date: 2026-04-29
---

# WC 2026 Model Accuracy & Edge Finder

## Problem

The current ensemble-v2 (Elo + Form + xG-Poisson, equal weights) achieves log-loss 1.054 and 43.8% accuracy on the WC 2022 backtest vs Pinnacle's benchmark of ~0.97 / 47%. More critically, only **2 of 15 golden zone games** had genuine edge against Pinnacle closing lines. The primary gaps:

1. **xG-Poisson is undertrained** — only 115 matches have real StatsBomb xG (WC 2018 + Euro 2020). The model uses goals fallback for 9,837 of 10,128 training matches.
2. **No squad/lineup quality signal** — team strength is inferred from historical results, not from current player quality. Market-beating edge often comes from knowing a squad is stronger or weaker than its reputation.
3. **No market comparison layer** — the model produces probabilities but doesn't systematically compare them to Kalshi or Pinnacle to surface bettable games.

## Goal

Ship a model upgrade before WC 2026 kickoff (June 11) that:
1. Incorporates current squad xG ratings into the Poisson model
2. Expands xG training data with Nations League and WC qualifying matches
3. Adds Pinnacle + Kalshi as comparison signals
4. Outputs a **double-edge filter**: flag games where model beats Pinnacle by ≥3% AND Kalshi is pricing below Pinnacle

## Success Criteria

- xG-Poisson accuracy improves vs WC 2022 backtest baseline (40.6%)
- Ensemble-v2 log-loss improves from 1.054 toward 1.00
- Double-edge filter produces a ranked table of actionable bets before each match-day
- At least 5+ games identified with genuine double-edge signal across WC 2026 group stage
- No data leakage: all improvements validated on WC 2022 test set before applying to 2026

## Scope

### In

**Improvement 1 — Lineup-based xG ratings in the Poisson model**
- Use `data/derived/team_attack_ratings.parquet` (already built) as the team strength input to the xG-Poisson
- `attack_rating` replaces raw historical xG as the Poisson λ parameter
- Re-run WC 2022 backtest with lineup-enhanced Poisson to measure improvement
- Data already exists: no new pull required

**Improvement 2 — Expand xG training data**
- Pull StatsBomb event data for UEFA Nations League 2022-23 and 2024-25 (free open data, already confirmed available)
- Add to xG training set alongside WC 2018 + Euro 2020
- Target: grow from 115 → 250+ matches with real StatsBomb xG
- Re-run backtest to measure impact

**Improvement 3 — Pinnacle market signal (4th model)**
- Pull Pinnacle closing odds via The Odds API for WC 2026 fixtures
- Devig using Power method (already in plan, Unit 4)
- Add devigged Pinnacle probability as a 4th signal alongside Elo, Form, xG-Poisson
- Weight: start equal (25%) then tune after backtest

**Improvement 4 — Double-edge filter output**
- For each WC 2026 match, compute:
  - `edge_vs_pinnacle = p_model - p_pinnacle_devigged`
  - `edge_vs_kalshi = p_model - p_kalshi_devigged`
  - `kalshi_vs_pinnacle = p_pinnacle_devigged - p_kalshi_devigged` (Kalshi underpricing vs sharp market)
- Flag as **DOUBLE EDGE** when:
  - `edge_vs_pinnacle ≥ 3%` (model beats sharpest book)
  - `edge_vs_kalshi ≥ 3%` (model beats betting market)
  - All 3 independent models agree (golden zone)
- Output as a ranked table sorted by `edge_vs_pinnacle` descending

### Out

- Meta-model (logistic regression on model outputs) — deferred. Need WC 2026 results to train it.
- Opponent-weighted form — deferred. Valuable but lower priority than lineup ratings + market signal.
- Altitude, rest days, travel distance — deferred. Marginal gains vs the above.
- Automated bet placement — never in scope. Manual execution only.

## Data

### What We Have (Ready Now)

| File | Content | Nations covered |
|---|---|---|
| `data/derived/team_attack_ratings.parquet` | Squad xG ratings, 52 nations | All 33 StatsBomb nations |
| `data/derived/squad_xg_ratings.parquet` | Player-level blended xG | 1,275 players |
| `data/derived/statsbomb_team_xg.parquet` | Match-level xG, WC18/Euro20/WC22/Euro24/Copa24 | 33 nations |
| `data/derived/understat_player_xg.parquet` | Club xG/90, 2022-25 | 5,078 players, top-6 leagues |
| `data/raw/martj42/latest/results.csv` | All match results through March 2026 | All 48 nations |
| `data/raw/kalshi/` | Weekly Kalshi market snapshots | All WC 2026 markets |

### Data Gaps — Ranked by Impact

#### Gap 1 — AFCON 2023 not yet pulled *(HIGH impact, FREE, pull today)*

StatsBomb has African Cup of Nations 2023 free. Pulling it gives xG event data for 7 nations currently missing from our model.

| Nation | Current coverage | After AFCON pull |
|---|---|---|
| Algeria | Elo + Form only | + StatsBomb xG |
| Egypt | Elo + Form only | + StatsBomb xG |
| Ghana | Elo + Form only | + StatsBomb xG |
| Morocco | Elo + Form only (has WC22 data via martj42) | + StatsBomb xG |
| Senegal | Partial (WC22 StatsBomb) | + AFCON xG |
| South Africa | Elo + Form only | + StatsBomb xG |
| Tunisia | Partial (WC22 StatsBomb) | + AFCON xG |

**How to get it:** Add to `TARGETS` in `tools/pull_statsbomb.py`:
```python
{"slug": "afcon2023", "competition_id": 1267, "season_id": 107, "label": "African Cup of Nations 2023"}
```
Then re-run `tools/aggregate_statsbomb_players.py`. Zero cost.

**After this pull: 36/48 WC 2026 nations have StatsBomb xG data.**

---

#### Gap 2 — 12 nations with zero StatsBomb event data *(MEDIUM impact — Elo+Form fallback)*

Even after pulling AFCON, these nations remain StatsBomb-blind:

| Nation | Confederation | Reason | Best fallback |
|---|---|---|---|
| Bosnia and Herzegovina | UEFA | Not in Euro 2024 | martj42 form + Elo |
| Norway | UEFA | Not in Euro 2024 | martj42 form + Elo |
| Sweden | UEFA | Not in Euro 2024 | martj42 form + Elo |
| Cape Verde | CAF | Small nation, AFCON group stage exit | martj42 form + Elo |
| DR Congo | CAF | Not in AFCON 2023 | martj42 form + Elo |
| Ivory Coast | CAF | Not in AFCON 2023 final stages | martj42 form + Elo |
| Haiti | CONCACAF | No major tournament data | martj42 form + Elo |
| Curaçao | CONCACAF | Debut nation | martj42 form + Elo |
| Iraq | AFC | Not in Asian Cup free data | martj42 form + Elo |
| Jordan | AFC | Not in Asian Cup free data | martj42 form + Elo |
| Uzbekistan | AFC | Not in Asian Cup free data | martj42 form + Elo |
| New Zealand | OFC | Only OFC qualifier | martj42 form + Elo |

**These 12 nations get Elo + Form only.** This is acceptable — most are lower seeds unlikely to generate Kalshi edge games. Bosnia and Norway are the two worth flagging since they're UEFA sides that could face top teams.

**Partial fix available:** Bosnia, Norway, Sweden all have players in Understat top-6 leagues. Even without national team event data, we can build a team xG rating from club-based player data by pulling squad lists when they're released.

---

#### Gap 3 — xG for Nations League and WC Qualifying *(MEDIUM impact — not in StatsBomb free data)*

StatsBomb does **not** include Nations League or WC qualifying in the free tier. This is the biggest missing training signal for the xG-Poisson model.

| Competition | Matches available | xG source | Status |
|---|---|---|---|
| UEFA Nations League 2022-23 | ~100 | Not in StatsBomb free | No free source found |
| UEFA Nations League 2024-25 | ~100 | Not in StatsBomb free | No free source found |
| CONMEBOL WC Qualifying 2026 | ~180 | Not in StatsBomb free | No free source found |
| CONCACAF Nations League | ~80 | Not in StatsBomb free | No free source found |

**Fallback:** martj42 has all qualifying results (goals, not xG). The xG-Poisson falls back to goals for these matches — same as it does today. No regression, just no improvement from qualifying data.

**Future option:** FBref has xG for national team competitions but is blocked by Cloudflare. If Cloudflare protection relaxes or a browser automation approach is added, this unlocks ~500 more training matches with real xG.

---

#### Gap 4 — Players outside Understat top-6 leagues *(MEDIUM impact — 692 players missing club xG)*

Understat covers EPL, Bundesliga, La Liga, Serie A, Ligue 1, RFPL. Players in other leagues have no 2024-25 club xG and fall back to national team xG only.

**Highest-impact missing leagues by nation:**

| League | Key nations affected | Players missing |
|---|---|---|
| MLS | USA, Canada, Mexico + CONMEBOL players | ~150+ |
| Liga MX | Mexico | ~24 |
| Brazilian Série A | Brazil | ~24 |
| Saudi Pro League | Saudi Arabia | ~16 |
| Persian Gulf Pro League | Iran | ~19 |
| J-League | Japan | ~11 |
| K-League | South Korea | ~7 |

**How to get it — MLS:** StatsBomb free data includes **MLS 2023** (`competition_id=44, season_id=107`). This covers players like Riqui Puig, Lorenzo Insigne, Xherdan Shaqiri who appeared for their national teams. Not xG by match, but adds coverage for CONCACAF/European players who moved to MLS.

Add to `TARGETS` in `tools/pull_statsbomb.py`:
```python
{"slug": "mls2023", "competition_id": 44, "season_id": 107, "label": "MLS 2023"}
```

**For Liga MX, Brazilian Série A, Saudi League:** No free xG source currently available. Fall back to national team data.

---

#### Gap 5 — Pinnacle odds *(HIGH impact for edge detection — needs API key)*

Pinnacle closing odds are the sharpest probability signal available. Comparing our model to Pinnacle tells us exactly where we have genuine edge.

**How to get it:**
1. Sign up at `theOddsApi.com` — free tier gives 500 credits/month
2. `soccer_fifa_world_cup` sport key will activate once WC 2026 is in the active schedule (~May 2026)
3. One call to `/v4/sports/soccer_fifa_world_cup/odds?regions=eu&markets=h2h` returns all matches + Pinnacle odds, costs ~2 credits
4. 500 free credits/month = 250 pulls = enough for daily polling during the tournament

**Cost:** $0 on free tier for our polling cadence. $30/mo if we want historical odds for backtesting.

**Required action:** Add `ODDS_API_KEY` to `.env` — no code changes needed once key exists (already planned in Unit 3 of the implementation plan).

---

#### Gap 6 — Official WC 2026 squad lists *(READY SOON — May 28)*

FIFA requires official 26-man squads to be submitted ~14 days before kickoff. Expected: **~May 28, 2026**.

**Current state:** We have likely squads from StatsBomb national team appearances (players who appeared in WC 2022 / Euro 2024 / Copa 2024 / AFCON 2023) — 1,275 players across 36 nations.

**Plan when squads drop:**
1. Re-run `tools/pull_wc2026_squads.py` — Wikipedia squad page will be populated
2. Diff against current `data/derived/squad_xg_ratings.parquet` to flag new players (call-ups not in our DB) and dropped players
3. For new call-ups: manually look up Understat or StatsBomb name, add to squad ratings
4. Re-compute `data/derived/team_attack_ratings.parquet` with official 26-man lists

---

### Data Acquisition Summary

| Gap | Impact | Cost | When | Action |
|---|---|---|---|---|
| AFCON 2023 not pulled | High | Free | **Now** | Add to `pull_statsbomb.py`, run today |
| MLS 2023 not pulled | Medium | Free | **Now** | Add to `pull_statsbomb.py`, run today |
| Pinnacle odds | High | Free tier ($0) | May 2026 | Add `ODDS_API_KEY` to `.env` |
| Official squad lists | High | Free | ~May 28 | Re-run `pull_wc2026_squads.py` |
| Nations League xG | Medium | No free source | Deferred | FBref if Cloudflare unblocks |
| Liga MX / Brazilian Série A xG | Medium | No free source | Deferred | Accept goals fallback |
| 12 nations no StatsBomb | Low | Free (partial) | Now | Bosnia/Norway/Sweden: use club data |

## The Double-Edge Model

```
For each WC 2026 match:

  Step 1: Run 4 models
    p_elo    = Elo model probability
    p_form   = Form-last-10 probability
    p_xgp    = xG-Poisson (with lineup ratings) probability
    p_pinny  = Power-devigged Pinnacle closing probability

  Step 2: Compute ensemble-v3
    p_model  = (p_elo + p_form + p_xgp + p_pinny) / 4

  Step 3: Disagreement filter
    disagreement = std([p_elo, p_form, p_xgp])  ← exclude Pinnacle from disagreement check
    if disagreement > 0.15 → skip (3-way split)

  Step 4: Double-edge filter
    edge_vs_pinnacle = p_model - p_pinny_devigged
    edge_vs_kalshi   = p_model - p_kalshi_devigged
    kalshi_below_pinnacle = p_kalshi_devigged < p_pinny_devigged

    ACTIONABLE if:
      edge_vs_pinnacle ≥ 0.03  AND
      edge_vs_kalshi   ≥ 0.03  AND
      kalshi_below_pinnacle     AND
      all 3 independent models agree
```

## Output — Weekly Bet Table

```
DOUBLE-EDGE BETS — WC 2026 Group Stage
Generated: 2026-06-05

Match              Outcome  p_model  p_pinny  edge_pinny  p_kalshi  edge_kalshi  Kalshi_odds  ½Kelly
─────────────────────────────────────────────────────────────────────────────────────────────────────
France vs X        France   0.64     0.58     +6.0%       0.51      +13.0%       1.96         3.2%bk
Brazil vs Y        Brazil   0.71     0.67     +4.0%       0.60      +11.0%       1.67         2.1%bk
...

Legend: ½Kelly = half-Kelly stake as % of bankroll. Cap at 2% per bet.
Bet only when: edge_pinny ≥ 3% AND edge_kalshi ≥ 3% AND models agree.
```

## Validation Plan

Before using on WC 2026:
1. Re-run full WC 2022 backtest with lineup ratings + expanded xG training
2. Compare log-loss and golden zone count vs current ensemble-v2 baseline
3. If improvement < 5% on log-loss, investigate before proceeding
4. Backtest double-edge filter on WC 2022 using historical Pinnacle odds

## Phasing (6 weeks to kickoff)

| Week | Task | Outcome |
|---|---|---|
| Week 1 (now) | Wire in lineup ratings to Poisson; pull Nations League xG | Improved xG-Poisson |
| Week 2 | Add Pinnacle as 4th signal; build double-edge filter | Full comparison table |
| Week 3 | Run WC 2022 backtest validation; tune if needed | Validated model |
| Week 4–5 | Update squad ratings as official squads drop (~May 28) | Fresh lineup data |
| Week 6 | Final table; identify first round bets | Actionable bet list |

## What This Doesn't Fix

- **False consensus losses** (Argentina vs Saudi Arabia, Cameroon vs Brazil) — no model catches all-team upsets. The 2% bankroll cap is the mitigation.
- **Kalshi liquidity** — pre-tournament markets have low volume. Double-edge filter helps but we still monitor `volume > 0` before placing.
- **15 nations with no StatsBomb data** — Algeria, Cape Verde, Bosnia, etc. fall back to Elo+Form only. Lower confidence on those matches.

## Related Docs

- `compound-model/docs/brainstorms/2026-04-28-wc2022-backtest-xg-ensemble-requirements.md` — the backtest that produced the baseline numbers
- `docs/solutions/best-practices/model-roles-and-best-use-2026-04-28.md` — when to use each model
- `docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md` — disagreement taxonomy and golden zone rule
- `compound-model/docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md` — full implementation plan (Units 1-13)
