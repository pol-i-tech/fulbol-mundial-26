# FableGoose vs DraftKings — Group-Stage Edges (2026-06-11 snapshot)

Side-by-side comparison of the **pure DC-Elo Poisson model** (FableGoose unblended) against the **de-vigged DraftKings 1X2** for all 72 group-stage fixtures.

> **Why the unblended model?** FableGoose's published `predictions.csv` is already 25% model / 75% market by design. Subtracting market from a market-weighted blend hides edge. The numbers below use `p_home_win` / `p_draw` / `p_away_win` from the upstream model output — the part of FableGoose that has an opinion *independent* of DK.

> **Status: analysis, not bet recommendations.** Per `DEVELOPMENT.md`, FableGoose is research-grade until guardrails pass. Big edges below are also where the model is most likely to be wrong — Elo + Dixon-Coles has no view on squad availability, fatigue, or tournament-specific motivation.

## How to read this

- **Edge (pp)** = `p_model − p_market`, in percentage points. Positive means the model thinks the market is **underpricing** that outcome.
- **Fair odds** = American odds implied by the model's probability. Compare to **Mkt odds** = de-vigged DK price. If the *actual* DK price is longer than the fair odds, that's where positive expected value lives.
- All 72 group matches matched against DK odds — no missing prices.

## Top positive edges (model says market is too short)

| Date | Match | Outcome | Model | Market | Edge | Fair → Mkt |
|---|---|---|---:|---:|---:|---|
| 2026-06-17 | Ghana v Panama | **away (Panama)** | 0.565 | 0.263 | **+30.2 pp** | -130 → +280 |
| 2026-06-14 | Ivory Coast v Ecuador | **away (Ecuador)** | 0.625 | 0.394 | +23.1 pp | -167 → +154 |
| 2026-06-25 | Ecuador v Germany | **home (Ecuador)** | 0.392 | 0.201 | +19.2 pp | +155 → +399 |
| 2026-06-11 | Mexico v South Africa | **home (Mexico)** | 0.807 | 0.616 | +19.1 pp | -418 → -160 |
| 2026-06-26 | Egypt v Iran | **away (Iran)** | 0.445 | 0.264 | +18.1 pp | +125 → +278 |
| 2026-06-12 | Canada v Bosnia | **home (Canada)** | 0.699 | 0.530 | +16.9 pp | -233 → -113 |
| 2026-06-21 | Belgium v Iran | **away (Iran)** | 0.283 | 0.120 | +16.3 pp | +253 → +735 |
| 2026-06-25 | Japan v Sweden | **home (Japan)** | 0.616 | 0.455 | +16.2 pp | -161 → +120 |
| 2026-06-16 | Austria v Jordan | **away (Jordan)** | 0.258 | 0.101 | +15.7 pp | +287 → +891 |
| 2026-06-12 | USA v Paraguay | **away (Paraguay)** | 0.385 | 0.240 | +14.5 pp | +160 → +317 |
| 2026-06-25 | Curaçao v Ivory Coast | **home (Curaçao)** | 0.211 | 0.074 | +13.7 pp | +373 → +1250 |
| 2026-06-27 | Croatia v Ghana | **home (Croatia)** | 0.710 | 0.576 | +13.4 pp | -244 → -136 |
| 2026-06-24 | South Africa v South Korea | **away (South Korea)** | 0.619 | 0.489 | +13.0 pp | -162 → +105 |
| 2026-06-24 | Mexico v Czech Republic | **home (Mexico)** | 0.659 | 0.533 | +12.6 pp | -194 → -114 |

Watchouts on the top of this list:
- **Ghana v Panama (+30 pp on Panama)** is so far from market that something is off: model has Elo South Africa-style imbalance but the market is treating Ghana as a clear favorite. Likely the Elo dataset has Panama and Ghana close while the market has access to qualification form / squad info that Elo doesn't. **Sanity-check before sizing.**
- **Curaçao v Ivory Coast (+13.7 pp home Curaçao at +1250)** is a long-shot edge. Pure model says ~21% but the market gives 7%. A 7%-vs-21% gap on a +1250 dog matters for parlay/futures but not for unit stakes — both numbers could easily be wrong by 5 pp.
- **Mexico, Canada, Croatia** edges all sit on the home side, which is plausible — DK may discount host/CONCACAF home advantage less than the Elo +100 implies.

## Top negative edges (model says market is too long)

| Date | Match | Outcome | Model | Market | Edge | Fair → Mkt |
|---|---|---|---:|---:|---:|---|
| 2026-06-17 | Ghana v Panama | home (Ghana) | 0.182 | 0.458 | **−27.5 pp** | +448 → +118 |
| 2026-06-25 | Curaçao v Ivory Coast | away (Ivory Coast) | 0.523 | 0.788 | −26.5 pp | -110 → -372 |
| 2026-06-16 | Austria v Jordan | home (Austria) | 0.462 | 0.725 | −26.3 pp | +116 → -263 |
| 2026-06-21 | Belgium v Iran | home (Belgium) | 0.432 | 0.681 | −24.9 pp | +131 → -213 |
| 2026-06-25 | Ecuador v Germany | away (Germany) | 0.319 | 0.553 | −23.4 pp | +214 → -124 |
| 2026-06-23 | Portugal v Uzbekistan | home (Portugal) | 0.578 | 0.773 | −19.5 pp | -137 → -341 |
| 2026-06-19 | USA v Australia | home (USA) | 0.371 | 0.543 | −17.2 pp | +169 → -119 |
| 2026-06-19 | Brazil v Haiti | home (Brazil) | 0.726 | 0.889 | −16.3 pp | -265 → -800 |
| 2026-06-14 | Germany v Curaçao | home (Germany) | 0.746 | 0.909 | −16.2 pp | -294 → -998 |
| 2026-06-13 | Brazil v Morocco | home (Brazil) | 0.432 | 0.593 | −16.1 pp | +131 → -146 |

The negative-edge list is mostly the **mirror of the positive-edge list** (Ghana/Panama, Curaçao/CIV, Austria/Jordan, etc.) — same disagreements seen from the other side. Where the same match appears in both tables, the strongest signal is whichever side has the longer market price (more edge per dollar risked).

The standalone heavyweight items — Brazil v Haiti, Germany v Curaçao, Portugal v Uzbekistan — are cases where the market is **even more confident than Elo** in the favorite. That's typical for heavy favorites: the market is using info Elo doesn't have (e.g., player-quality gap). **Do not** read these as "fade the favorite" — they're cases where the model probably under-confident, not the market over-confident.

## Modal-pick disagreements (11 of 72 matches)

These are the matches where the model and the market **disagree on the favorite**, not just the magnitude. Highest-signal targets for further investigation.

| Date | Match | Model pick (p) | Market pick (p) |
|---|---|---|---|
| 2026-06-11 | South Korea v Czech Republic | **home** (0.446) | away (0.353) |
| 2026-06-12 | USA v Paraguay | **away** (0.385) | home (0.485) |
| 2026-06-17 | Ghana v Panama | **away** (0.565) | home (0.458) |
| 2026-06-24 | Canada v Switzerland | **home** (0.386) | away (0.447) |
| 2026-06-25 | USA v Turkey | **away** (0.413) | home (0.376) |
| 2026-06-25 | Ecuador v Germany | **home** (0.392) | away (0.553) |
| 2026-06-26 | Egypt v Iran | **away** (0.445) | home (0.419) |
| 2026-06-26 | Cape Verde v Saudi Arabia | **away** (0.387) | home (0.369) |
| 2026-06-27 | Algeria v Austria | **home** (0.364) | away (0.434) |
| 2026-06-27 | Colombia v Portugal | **home** (0.385) | away (0.438) |
| 2026-06-27 | DR Congo v Uzbekistan | **away** (0.408) | home (0.409) — coin flip |

Recurring pattern: in matches involving **US hosts (USA, MEX, CAN)**, the model frequently overweights the home-advantage Elo bonus and disagrees with the market about home-favorite status (USA v Paraguay, Canada v Switzerland are flips; USA v Turkey, USA v Australia get heavy negative edges on home). Worth a deliberate look at whether +100 Elo for hosts is justified at WC2026 or should be smaller.

## High-conviction agreements (both pick the same; model more confident)

When both agree on the favorite and the model is *more* confident than the market, these are the cleanest "the market is just shading away from a real favorite" candidates.

| Date | Match | Pick | Model | Market | Δ |
|---|---|---|---:|---:|---:|
| 2026-06-14 | Ivory Coast v Ecuador | away | 0.625 | 0.394 | +23.1 pp |
| 2026-06-11 | Mexico v South Africa | home | 0.807 | 0.616 | +19.1 pp |
| 2026-06-12 | Canada v Bosnia | home | 0.699 | 0.530 | +16.9 pp |
| 2026-06-25 | Japan v Sweden | home | 0.616 | 0.455 | +16.2 pp |
| 2026-06-27 | Croatia v Ghana | home | 0.710 | 0.576 | +13.4 pp |
| 2026-06-24 | South Africa v South Korea | away | 0.619 | 0.489 | +13.0 pp |
| 2026-06-24 | Mexico v Czech Republic | home | 0.659 | 0.533 | +12.6 pp |
| 2026-06-23 | England v Ghana | home | 0.836 | 0.730 | +10.6 pp |
| 2026-06-20 | Tunisia v Japan | away | 0.646 | 0.559 | +8.8 pp |
| 2026-06-22 | Argentina v Austria | home | 0.670 | 0.586 | +8.5 pp |

## How to use this list

1. **Cross-check against another contributor's model** — `results/ensemble-e3/` and `results/compound-model/` are the obvious comparisons. If three independent methods all show Panama / Iran / Jordan / Curaçao as relative live dogs, that's a real signal. If only FableGoose does, it's probably an Elo-without-context artifact.
2. **Verify the actual book price** — these comparisons use de-vigged DK from `data/raw/market_odds_dk.csv`, which is a snapshot. Prices move. Pull live prices before sizing.
3. **The model is research-grade.** No row in `predictions.csv` is tagged `high` confidence. Treat every line above as a *hypothesis to test* against the field-of-models, not a green light.

## Data sources

- Model probabilities: `predictions_2026_group_blended.csv` columns `p_home_win` / `p_draw` / `p_away_win`
- Market probabilities: same file, columns `p_home_mkt` / `p_draw_mkt` / `p_away_mkt` (vig-stripped DraftKings 1X2)
- Per-row CSV with every match × outcome: [`edges.csv`](./edges.csv)
