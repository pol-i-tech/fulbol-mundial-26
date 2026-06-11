# WC2026 — what the data actually predicts

Run off `data/wc2026.duckdb` — FIFA ranking, squad-aggregated player xG (attack/defense), and recent form — through 20,000 Monte Carlo tournaments (seed 42). Economics and individual players are **narrative color only**; they never touch the prediction engine.

## The model's favorite: **Argentina** (11.2%)

| Rank | Team | Champion | Final | Semi | Quarter |
|---|---|---|---|---|---|
| 1 | Argentina | 11.2% | 17.8% | 27.3% | 40.1% |
| 2 | France | 10.3% | 16.8% | 25.9% | 39.5% |
| 3 | England | 9.0% | 15.0% | 24.1% | 37.0% |
| 4 | Portugal | 7.8% | 13.8% | 22.4% | 36.5% |
| 5 | Spain | 7.2% | 12.7% | 21.0% | 32.3% |
| 6 | Germany | 6.7% | 12.7% | 21.7% | 35.2% |
| 7 | Brazil | 5.9% | 11.0% | 19.4% | 33.9% |
| 8 | Netherlands | 5.6% | 10.2% | 18.6% | 32.5% |

**No thumb on the scale.** The popular pre-tournament chatter liked Spain and the Netherlands. The model doesn't fully agree — it has the four most-talked-about contenders at: Spain 7.2%, Netherlands 5.6%, Argentina 11.2%, Portugal 7.8%. It rates **Argentina** the most likely winner regardless of the narrative. The numbers below are the model's, not anyone's hopes.

## The 12 groups — what the model sees

### Group A
Projected finish: **Mexico** (9pts) → **Czechia** (4pts) → **South Korea** (2pts) → **South Africa** (1pts)
- 🥇 **Mexico** win it, **Czechia** follow them through. **South Korea** sneaks through as a best-third; **South Africa** finish bottom.
- **South Korea vs Czechia** is a genuine three-way coin-flip (29.5% / 36.6% / 33.9%).
- David-watch: **Czechia** (10.9M people, $31.8k/capita) is dwarfed by Mexico — ~12× the population.

### Group B
Projected finish: **Switzerland** (9pts) → **Canada** (6pts) → **Bosnia and Herzegovina** (3pts) → **Qatar** (0pts)
- 🥇 **Switzerland** win it, **Canada** follow them through. **Bosnia and Herzegovina** sneaks through as a best-third; **Qatar** finish bottom.
- **Switzerland vs Canada** is too close to call (36.9% / 32.4% / 30.7%).
- David-watch: **Qatar** (2.9M people, $76.7k/capita) is dwarfed by Canada — ~14× the population.

### Group C
Projected finish: **Brazil** (9pts) → **Morocco** (6pts) → **Scotland** (3pts) → **Haiti** (0pts)
- 🥇 **Brazil** win it, **Morocco** follow them through. **Scotland** sneaks through as a best-third; **Haiti** finish bottom.
- The model's surest thing here: **Brazil 58.3%** to beat Haiti.
- David-watch: **Haiti** (11.8M people, $2.1k/capita) is dwarfed by Brazil — ~18× the population.

### Group D
Projected finish: **USA** (9pts) → **Türkiye** (4pts) → **Australia** (2pts) → **Paraguay** (1pts)
- 🥇 **USA** win it, **Türkiye** follow them through. **Australia** goes home despite third; **Paraguay** finish bottom.
- **Paraguay vs Australia** is a genuine three-way coin-flip (28.7% / 39.9% / 31.4%).
- David-watch: **Paraguay** (6.9M people, $6.4k/capita) is dwarfed by USA — ~49× the population.

### Group E
Projected finish: **Germany** (9pts) → **Ivory Coast** (4pts) → **Ecuador** (4pts) → **Curaçao** (0pts)
- 🥇 **Germany** win it, **Ivory Coast** follow them through. **Ecuador** sneaks through as a best-third; **Curaçao** finish bottom.
- The model's surest thing here: **Germany 61.4%** to beat Curaçao.
- **Ivory Coast vs Ecuador** is too close to call (29.4% / 38.1% / 32.5%).
- David-watch: **Curaçao** (156k people, $22.8k/capita) is dwarfed by Germany — ~535× the population.

### Group F
Projected finish: **Netherlands** (9pts) → **Japan** (6pts) → **Sweden** (1pts) → **Tunisia** (1pts)
- 🥇 **Netherlands** win it, **Japan** follow them through. **Sweden** goes home despite third; **Tunisia** finish bottom.
- David-watch: **Sweden** (10.6M people, $57.1k/capita) is dwarfed by Japan — ~12× the population.

### Group G
Projected finish: **Belgium** (9pts) → **Egypt** (6pts) → **Iran** (3pts) → **New Zealand** (0pts)
- 🥇 **Belgium** win it, **Egypt** follow them through. **Iran** sneaks through as a best-third; **New Zealand** finish bottom.
- **Egypt vs Iran** is a genuine three-way coin-flip (35.1% / 33.7% / 31.2%).
- David-watch: **New Zealand** (5.3M people, $49.2k/capita) is dwarfed by Egypt — ~22× the population.

### Group H
Projected finish: **Spain** (9pts) → **Uruguay** (6pts) → **Saudi Arabia** (1pts) → **Cape Verde** (1pts)
- 🥇 **Spain** win it, **Uruguay** follow them through. **Saudi Arabia** goes home despite third; **Cape Verde** finish bottom.
- The model's surest thing here: **Spain 57.1%** to beat Cape Verde.
- **Cape Verde vs Saudi Arabia** is a genuine three-way coin-flip (26.8% / 38.7% / 34.5%).
- David-watch: **Cape Verde** (525k people, $5.2k/capita) is dwarfed by Spain — ~93× the population.

### Group I
Projected finish: **France** (9pts) → **Senegal** (6pts) → **Norway** (3pts) → **Iraq** (0pts)
- 🥇 **France** win it, **Senegal** follow them through. **Norway** sneaks through as a best-third; **Iraq** finish bottom.
- The model's surest thing here: **France 59.5%** to beat Iraq.
- David-watch: **Norway** (5.6M people, $86.8k/capita) is dwarfed by France — ~12× the population.

### Group J
Projected finish: **Argentina** (9pts) → **Austria** (6pts) → **Algeria** (3pts) → **Jordan** (0pts)
- 🥇 **Argentina** win it, **Austria** follow them through. **Algeria** sneaks through as a best-third; **Jordan** finish bottom.
- The model's surest thing here: **Argentina 59.5%** to beat Jordan.
- David-watch: **Austria** (9.2M people, $58.3k/capita) is dwarfed by Algeria — ~5× the population.

### Group K
Projected finish: **Portugal** (9pts) → **Colombia** (6pts) → **DR Congo** (1pts) → **Uzbekistan** (1pts)
- 🥇 **Portugal** win it, **Colombia** follow them through. **DR Congo** goes home despite third; **Uzbekistan** finish bottom.
- The model's surest thing here: **Portugal 56.1%** to beat Uzbekistan.
- **DR Congo vs Uzbekistan** is too close to call (34.6% / 37.0% / 28.4%).
- David-watch: **Portugal** (10.7M people, $29.3k/capita) is dwarfed by DR Congo — ~10× the population.

### Group L
Projected finish: **England** (9pts) → **Croatia** (6pts) → **Panama** (3pts) → **Ghana** (0pts)
- 🥇 **England** win it, **Croatia** follow them through. **Panama** sneaks through as a best-third; **Ghana** finish bottom.
- The model's surest thing here: **England 57.3%** to beat Panama.
- **Ghana vs Panama** is a genuine three-way coin-flip (28.9% / 34.8% / 36.3%).
- David-watch: **Croatia** (3.9M people, $24.1k/capita) is dwarfed by England — ~18× the population.

## The knockouts — round by round

### Round of 32
The model expects 16 ties here — 5 comfortable for the favourite, 1 a genuine coin-flip that could swing on a single moment.
- **Canada** 36.2% vs **Czechia** — a tight, low-scoring grind — the models can't agree, a competitive, winnable-either-way match.
- **Germany** 54.4% vs **Bosnia and Herzegovina** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Netherlands** 39.7% vs **Morocco** — a tight, low-scoring grind — all three models agree, a competitive, winnable-either-way match.
- **Brazil** 43.1% vs **Japan** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **France** 56.1% vs **Iran** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Senegal** 43.7% vs **Ivory Coast** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Mexico** 37.3% vs **Ecuador** — a tight, low-scoring grind — the models can't agree, a competitive, winnable-either-way match.
- **England** 50.2% vs **Norway** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **USA** 41.5% vs **Algeria** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Belgium** 40.1% vs **South Korea** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Croatia** 41.3% vs **Colombia** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Spain** 45.6% vs **Austria** — a balanced contest — a competitive, winnable-either-way match.
- **Switzerland** 45.8% vs **Scotland** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Argentina** 48.0% vs **Uruguay** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Portugal** 54.9% vs **Panama** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Türkiye** 34.4% vs **Egypt** — a tight, low-scoring grind — a coin-flip that could go to extra time or penalties. ⚠️ coin-flip

### Round of 16
The model expects 8 ties here — 2 comfortable for the favourite, 1 a genuine coin-flip that could swing on a single moment.
- **France** 41.5% vs **Germany** — an open, end-to-end affair — a competitive, winnable-either-way match.
- **Netherlands** 43.0% vs **Canada** — a balanced contest — a competitive, winnable-either-way match.
- **Brazil** 40.6% vs **Senegal** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **England** 48.8% vs **Mexico** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Spain** 39.3% vs **Croatia** — a balanced contest — a competitive, winnable-either-way match.
- **USA** 34.4% vs **Belgium** — a tight, low-scoring grind — the models can't agree, a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Argentina** 52.2% vs **Türkiye** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Portugal** 42.2% vs **Switzerland** — a balanced contest — all three models agree, a competitive, winnable-either-way match.

### Quarter-finals
The model expects 4 ties here.
- **France** 41.6% vs **Netherlands** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Spain** 44.4% vs **USA** — a balanced contest — a competitive, winnable-either-way match.
- **England** 39.0% vs **Brazil** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Argentina** 40.2% vs **Portugal** — a balanced contest — a competitive, winnable-either-way match.

### Semi-finals
The model expects 2 ties here — 1 a genuine coin-flip that could swing on a single moment.
- **France** 36.6% vs **England** — a balanced contest — a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Argentina** 37.7% vs **Spain** — a balanced contest — a competitive, winnable-either-way match.

## The final — and a champion

**France vs Argentina** at the model's projected final.

> A balanced contest — a coin-flip that could go to extra time or penalties.

Head-to-head the engine splits it **France 34.2% / draw 30.3% / Argentina 35.5%** (expected goals 1.997). 
This is no procession — it is the kind of final that lives on the edge of extra time, where one set-piece or one penalty decides a World Cup.

- **France** lean on: Randal Kolo Muani (0.92 xG/90), Kylian Mbappé (0.80 xG/90), Ousmane Dembélé (0.64 xG/90).
  - FIFA #1, UEFA, $46.1k/capita, 68.6M people.
- **Argentina** lean on: Lionel Messi (0.79 xG/90), Lautaro Martínez (0.72 xG/90), Gonzalo Montiel (0.52 xG/90).
  - FIFA #3, CONMEBOL, $14.0k/capita, 45.7M people.

### 🏆 Model's pick: **Argentina**
The simulation crowns **Argentina** (35.5% to win the final over France at 34.2%), and 11.2% to lift the trophy across all 20,000 simulated tournaments.

## Known limitations — read before you trust the bracket

The top teams' attack ratings have been **refreshed to their actual 2026 squads** (current clubs, recent club xG), which tightened the race into a genuine FIFA-elite scrum rather than a runaway. Two honest caveats remain in the xG layer:

- **Some stars are frozen at their peak.** Lionel Messi (Argentina, 0.79 national xG/90), Romelu Lukaku (Belgium, 0.74 national xG/90), Cristiano Ronaldo (Portugal, 0.73 national xG/90) are rated purely on national-team tournament xG with **no recent club data** — so a player who lit up 2022–24 is treated as still at that level today, with age and current club form invisible to the model. It nudges the 2022-era powers up.
- **A structural gap stays:** club xG comes from Understat (top-5 leagues + RFPL only), so players in the Eredivisie, Saudi, MLS, Brazilian or Turkish leagues fall back to national-team xG. The roster refresh fixed *who* is in each squad and their European-club form; it can't conjure club xG for leagues we don't cover.

*Net effect: this is now strongest as a current-form ranking of the elite — the top eight sit within a few points of each other, so treat the bracket as a likelihood map, not a prophecy.*

## How to read this (the honest footer)

- **Engine:** `ensemble = 0.35·Elo(FIFA) + 0.45·xG-Poisson + 0.20·Form`, the config that matched Pinnacle's accuracy in the WC2022 backtest.
- **Match character** comes from the WC2022 *model-agreement taxonomy*: when all three component models agree ("golden-zone") the call is reliable even at modest confidence; when they three-way split, it's genuine noise — a coin-flip.
- **Economics & players are color only.** GDP and population never enter the engine, so the model can't be accused of downgrading teams that overperform their wealth (Argentina, Morocco, Senegal).
- **Reproducible:** seed 42, 20,000 simulations. Same seed → same report.
- Knockout matchups shown are the *modal* (most-likely) bracket; real draws will diverge, which is why per-team survival odds (the tables) matter more than any one projected tie.

*Full per-match probabilities in `per_game.csv`; data lineage in `DATA_LINEAGE.md`.*
