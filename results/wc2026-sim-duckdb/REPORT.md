# WC2026 — what the data actually predicts

Run off `data/wc2026.duckdb` — FIFA ranking, squad-aggregated player xG (attack/defense), and recent form — through 20,000 Monte Carlo tournaments (seed 42). Economics and individual players are **narrative color only**; they never touch the prediction engine.

## The model's favorite: **France** (16.0%)

| Rank | Team | Champion | Final | Semi | Quarter |
|---|---|---|---|---|---|
| 1 | France | 16.0% | 25.1% | 36.2% | 50.6% |
| 2 | Argentina | 12.7% | 20.3% | 30.1% | 44.2% |
| 3 | Portugal | 9.4% | 16.3% | 26.0% | 40.8% |
| 4 | Croatia | 6.3% | 11.9% | 21.1% | 34.3% |
| 5 | Brazil | 6.2% | 11.2% | 20.0% | 34.6% |
| 6 | England | 6.2% | 11.3% | 19.1% | 30.5% |
| 7 | Germany | 4.4% | 8.4% | 15.6% | 26.8% |
| 8 | Netherlands | 4.3% | 8.3% | 16.1% | 29.7% |

**No thumb on the scale.** The popular pre-tournament chatter liked Spain and the Netherlands. The model doesn't fully agree — it has the four most-talked-about contenders at: Spain 3.6%, Netherlands 4.3%, Argentina 12.7%, Portugal 9.4%. It rates **France** the most likely winner regardless of the narrative. The numbers below are the model's, not anyone's hopes.

## The 12 groups — what the model sees

### Group A
Projected finish: **Mexico** (9pts) → **Czechia** (6pts) → **South Korea** (3pts) → **South Africa** (0pts)
- 🥇 **Mexico** win it, **Czechia** follow them through. **South Korea** goes home despite third; **South Africa** finish bottom.
- **South Africa vs South Korea** is a genuine three-way coin-flip (31.1% / 33.6% / 35.3%).
- David-watch: **Czechia** (10.9M people, $31.8k/capita) is dwarfed by Mexico — ~12× the population.

### Group B
Projected finish: **Switzerland** (9pts) → **Canada** (6pts) → **Bosnia and Herzegovina** (3pts) → **Qatar** (0pts)
- 🥇 **Switzerland** win it, **Canada** follow them through. **Bosnia and Herzegovina** sneaks through as a best-third; **Qatar** finish bottom.
- **Bosnia and Herzegovina vs Qatar** is too close to call (36.4% / 33.2% / 30.4%).
- David-watch: **Qatar** (2.9M people, $76.7k/capita) is dwarfed by Canada — ~14× the population.

### Group C
Projected finish: **Brazil** (9pts) → **Morocco** (6pts) → **Scotland** (3pts) → **Haiti** (0pts)
- 🥇 **Brazil** win it, **Morocco** follow them through. **Scotland** goes home despite third; **Haiti** finish bottom.
- The model's surest thing here: **Brazil 57.1%** to beat Haiti.
- **Haiti vs Scotland** is a genuine three-way coin-flip (31.3% / 32.2% / 36.5%).
- David-watch: **Haiti** (11.8M people, $2.1k/capita) is dwarfed by Brazil — ~18× the population.

### Group D
Projected finish: **USA** (9pts) → **Türkiye** (4pts) → **Australia** (2pts) → **Paraguay** (1pts)
- 🥇 **USA** win it, **Türkiye** follow them through. **Australia** goes home despite third; **Paraguay** finish bottom.
- **Paraguay vs Australia** is a genuine three-way coin-flip (32.0% / 37.8% / 30.2%).
- David-watch: **Paraguay** (6.9M people, $6.4k/capita) is dwarfed by USA — ~49× the population.

### Group E
Projected finish: **Germany** (9pts) → **Ecuador** (6pts) → **Ivory Coast** (3pts) → **Curaçao** (0pts)
- 🥇 **Germany** win it, **Ecuador** follow them through. **Ivory Coast** sneaks through as a best-third; **Curaçao** finish bottom.
- The model's surest thing here: **Germany 56.5%** to beat Curaçao.
- David-watch: **Curaçao** (156k people, $22.8k/capita) is dwarfed by Germany — ~535× the population.

### Group F
Projected finish: **Netherlands** (9pts) → **Japan** (6pts) → **Sweden** (3pts) → **Tunisia** (0pts)
- 🥇 **Netherlands** win it, **Japan** follow them through. **Sweden** sneaks through as a best-third; **Tunisia** finish bottom.
- David-watch: **Sweden** (10.6M people, $57.1k/capita) is dwarfed by Japan — ~12× the population.

### Group G
Projected finish: **Belgium** (9pts) → **Egypt** (6pts) → **Iran** (3pts) → **New Zealand** (0pts)
- 🥇 **Belgium** win it, **Egypt** follow them through. **Iran** sneaks through as a best-third; **New Zealand** finish bottom.
- **Egypt vs Iran** is too close to call (35.6% / 32.5% / 31.9%).
- David-watch: **New Zealand** (5.3M people, $49.2k/capita) is dwarfed by Egypt — ~22× the population.

### Group H
Projected finish: **Spain** (9pts) → **Uruguay** (6pts) → **Saudi Arabia** (3pts) → **Cape Verde** (0pts)
- 🥇 **Spain** win it, **Uruguay** follow them through. **Saudi Arabia** sneaks through as a best-third; **Cape Verde** finish bottom.
- **Cape Verde vs Saudi Arabia** is a genuine three-way coin-flip (29.4% / 33.8% / 36.8%).
- David-watch: **Cape Verde** (525k people, $5.2k/capita) is dwarfed by Spain — ~93× the population.

### Group I
Projected finish: **France** (9pts) → **Senegal** (6pts) → **Norway** (3pts) → **Iraq** (0pts)
- 🥇 **France** win it, **Senegal** follow them through. **Norway** sneaks through as a best-third; **Iraq** finish bottom.
- The model's surest thing here: **France 61.9%** to beat Iraq.
- **Iraq vs Norway** is a genuine three-way coin-flip (30.3% / 31.8% / 37.9%).
- David-watch: **Norway** (5.6M people, $86.8k/capita) is dwarfed by France — ~12× the population.

### Group J
Projected finish: **Argentina** (9pts) → **Austria** (6pts) → **Algeria** (3pts) → **Jordan** (0pts)
- 🥇 **Argentina** win it, **Austria** follow them through. **Algeria** sneaks through as a best-third; **Jordan** finish bottom.
- The model's surest thing here: **Argentina 60.7%** to beat Jordan.
- **Algeria vs Austria** is too close to call (29.8% / 33.6% / 36.6%).
- David-watch: **Austria** (9.2M people, $58.3k/capita) is dwarfed by Algeria — ~5× the population.

### Group K
Projected finish: **Portugal** (9pts) → **Colombia** (6pts) → **DR Congo** (3pts) → **Uzbekistan** (0pts)
- 🥇 **Portugal** win it, **Colombia** follow them through. **DR Congo** sneaks through as a best-third; **Uzbekistan** finish bottom.
- The model's surest thing here: **Portugal 56.9%** to beat Uzbekistan.
- **DR Congo vs Uzbekistan** is too close to call (33.8% / 33.4% / 32.9%).
- David-watch: **Portugal** (10.7M people, $29.3k/capita) is dwarfed by DR Congo — ~10× the population.

### Group L
Projected finish: **England** (9pts) → **Croatia** (6pts) → **Panama** (3pts) → **Ghana** (0pts)
- 🥇 **England** win it, **Croatia** follow them through. **Panama** goes home despite third; **Ghana** finish bottom.
- The model's surest thing here: **England 56.2%** to beat Panama.
- **Ghana vs Panama** is too close to call (33.6% / 30.8% / 35.6%).
- David-watch: **Croatia** (3.9M people, $24.1k/capita) is dwarfed by England — ~18× the population.

## The knockouts — round by round

### Round of 32
The model expects 16 ties here — 4 comfortable for the favourite, 3 genuine coin-flips that could swing on a single moment.
- **Canada** 35.3% vs **Czechia** — a tight, low-scoring grind — the models can't agree, a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Germany** 54.6% vs **Bosnia and Herzegovina** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Netherlands** 39.3% vs **Morocco** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Brazil** 44.0% vs **Japan** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **France** 62.6% vs **Iran** — an open, end-to-end affair — all three models agree, a comfortable edge for the favorite.
- **Ecuador** 34.2% vs **Senegal** — a tight, low-scoring grind — the models can't agree, a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Mexico** 42.0% vs **Ivory Coast** — a balanced contest — a competitive, winnable-either-way match.
- **England** 52.3% vs **Saudi Arabia** — a balanced contest — a comfortable edge for the favorite.
- **USA** 40.4% vs **Norway** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Belgium** 42.0% vs **Algeria** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Croatia** 45.4% vs **Colombia** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Spain** 44.4% vs **Austria** — a tight, low-scoring grind — a competitive, winnable-either-way match.
- **Switzerland** 44.2% vs **Sweden** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Argentina** 48.3% vs **Uruguay** — an open, end-to-end affair — all three models agree, a competitive, winnable-either-way match.
- **Portugal** 56.5% vs **DR Congo** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Türkiye** 33.5% vs **Egypt** — a tight, low-scoring grind — a coin-flip that could go to extra time or penalties. ⚠️ coin-flip

### Round of 16
The model expects 8 ties here — 1 comfortable for the favourite, 2 genuine coin-flips that could swing on a single moment.
- **France** 48.3% vs **Germany** — an open, end-to-end affair — a competitive, winnable-either-way match.
- **Netherlands** 43.4% vs **Canada** — a balanced contest — a competitive, winnable-either-way match.
- **Brazil** 45.4% vs **Ecuador** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **England** 46.3% vs **Mexico** — a balanced contest — all three models agree, a competitive, winnable-either-way match.
- **Croatia** 36.9% vs **Spain** — a balanced contest — a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Belgium** 35.5% vs **USA** — a tight, low-scoring grind — the models can't agree, a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Argentina** 56.7% vs **Türkiye** — a balanced contest — all three models agree, a comfortable edge for the favorite.
- **Portugal** 45.2% vs **Switzerland** — an open, end-to-end affair — all three models agree, a competitive, winnable-either-way match.

### Quarter-finals
The model expects 4 ties here — 1 a genuine coin-flip that could swing on a single moment.
- **France** 47.9% vs **Netherlands** — an open, end-to-end affair — all three models agree, a competitive, winnable-either-way match.
- **Croatia** 41.8% vs **Belgium** — a balanced contest — a competitive, winnable-either-way match.
- **England** 36.9% vs **Brazil** — a balanced contest — a coin-flip that could go to extra time or penalties. ⚠️ coin-flip
- **Argentina** 41.0% vs **Portugal** — an open, end-to-end affair — a competitive, winnable-either-way match.

### Semi-finals
The model expects 2 ties here.
- **France** 43.6% vs **England** — an open, end-to-end affair — a competitive, winnable-either-way match.
- **Argentina** 43.3% vs **Croatia** — an open, end-to-end affair — all three models agree, a competitive, winnable-either-way match.

## The final — and a champion

**France vs Argentina** at the model's projected final.

> An open, end-to-end affair — a coin-flip that could go to extra time or penalties.

Head-to-head the engine splits it **France 37.8% / draw 27.7% / Argentina 34.5%** (expected goals 2.839). 
This is no procession — it is the kind of final that lives on the edge of extra time, where one set-piece or one penalty decides a World Cup.

- **France** lean on: Randal Kolo Muani (0.92 xG/90), Kylian Mbappé (0.80 xG/90), Ousmane Dembélé (0.64 xG/90).
  - FIFA #1, UEFA, $46.1k/capita, 68.6M people.
- **Argentina** lean on: Lionel Messi (0.79 xG/90), Lautaro Martínez (0.72 xG/90), Gonzalo Montiel (0.52 xG/90).
  - FIFA #3, CONMEBOL, $14.0k/capita, 45.7M people.

### 🏆 Model's pick: **France**
The simulation crowns **France** (37.8% to win the final over Argentina at 34.5%), and 16.0% to lift the trophy across all 20,000 simulated tournaments.

## Known limitations — read before you trust the bracket

Your eyes aren't wrong if this looks a bit *2022*. The engine tracks the current FIFA ranking closely, but the xG layer that breaks ties between near-equal sides leans on 2022–24 tournament form, and it has real coverage gaps. Two to keep in mind:

- **Spain is probably under-rated here.** FIFA #2 in the world, yet its squad-xG attack rating (0.32) sits well below the contender median (0.46) — closer to a mid-tier side than a title favourite. That's a squad-data coverage gap, not a football verdict, and it's why **Spain**'s 3.6% title odds look low for a top-2 team. Treat them as live regardless of the number.
- **Some stars are frozen at their peak.** Lionel Messi (Argentina, 0.79 national xG/90), Romelu Lukaku (Belgium, 0.74 national xG/90), Cristiano Ronaldo (Portugal, 0.73 national xG/90) are rated purely on national-team tournament xG with **no recent club data** — so a player who lit up 2022–24 is treated as still at that level today, with age and current club form invisible to the model. It nudges the 2022-era powers up.

*Net effect: the model is strongest as a current-form ranking and weakest where squad-xG data is thin. The honest takeaway — France and Argentina are genuinely elite right now, but the gap to Spain (and the tidy 2022 rematch) is partly a data artifact, not destiny.*

## How to read this (the honest footer)

- **Engine:** `ensemble = 0.35·Elo(FIFA) + 0.45·xG-Poisson + 0.20·Form`, the config that matched Pinnacle's accuracy in the WC2022 backtest.
- **Match character** comes from the WC2022 *model-agreement taxonomy*: when all three component models agree ("golden-zone") the call is reliable even at modest confidence; when they three-way split, it's genuine noise — a coin-flip.
- **Economics & players are color only.** GDP and population never enter the engine, so the model can't be accused of downgrading teams that overperform their wealth (Argentina, Morocco, Senegal).
- **Reproducible:** seed 42, 20,000 simulations. Same seed → same report.
- Knockout matchups shown are the *modal* (most-likely) bracket; real draws will diverge, which is why per-team survival odds (the tables) matter more than any one projected tie.

*Full per-match probabilities in `per_game.csv`; data lineage in `DATA_LINEAGE.md`.*
