---
title: WC2026 Prediction Report — Public Web Page
date: 2026-05-05
status: ready-for-planning
---

# WC2026 Prediction Report — Requirements

## Goal

A shareable, single-URL web report presenting the WC2026 simulation model to friends and statistician colleagues. The page must communicate that serious data work was done, be visually striking, and remain honest about data gaps.

## Audience

- Casual friends: understand that it's model-driven, see the predictions, have fun with it
- Statistician friends: appreciate the methodology depth, spot the data gaps, engage with the model-vs-market signal

---

## Design

### Aesthetic
- **Background:** Near-black (`#1a1a2e` or similar dark charcoal)
- **Font:** Monospace — `JetBrains Mono` or `Space Mono` (Google Fonts, free) — the terminal/code aesthetic shown in the reference screenshot
- **Tone:** Minimalistic, modern, techy, edgy, fun — not over-engineered UI, just clean and confident
- **Accent color:** One highlight color (e.g. a bright cyan `#00d4ff` or amber `#ffb703`) used sparingly for emphasis and active states

### Interaction States
- **Tab active:** accent color text + bottom border in accent color
- **Tab hover (inactive):** accent color text only, no border
- **Table row hover:** subtle background tint (`rgba(255,255,255,0.04)`)
- **Low-confidence badge:** muted red/orange `LOW` pill, no hover behavior needed

### Structure — Two Views
Single HTML file with **tab/toggle navigation** (no page reload):

| Tab | Content |
|-----|---------|
| `METHODOLOGY` | How the model works |
| `RESULTS` | Tournament bracket predictions |

A minimal top bar shows the two tabs. Active tab highlighted per states above. No sidebar, no complex nav.

---

## Section: Methodology

Tone: Simple, confident. Bullet-heavy. No jargon without a one-line explanation. The reader should finish this section thinking "okay, they actually built something serious."

### Subsections (in order)

**Data Sources**
- What data was collected (StatsBomb open data, Understat club xG, Kalshi/Polymarket market prices, international results going back to 2018)
- How many matches / players covered

**Models**
Four models, one-liner each:
- `ELO BASELINE` — time-decay Elo on 7,961 modern internationals; proven simple benchmark
- `POISSON GOALS` — attack/defense strength predicts goal distribution per match
- `LAST-10 FORM` — rolling form over each team's most recent 10 matches
- `ENSEMBLE` — weighted average of the three models above

**Simulation**
- 10,000 Monte Carlo tournament runs
- Respects the 12-group × 4 → top-2 + best-8-thirds → Round-of-32 bracket structure
- Includes extra time and penalty shootout modeling

**Feature Importance** _(brief callout)_
- Club xG (2024-25 season) — 60% weight — densest signal for most players
- National team xG history — 40% weight — tournament form adjustment
- Elo prior — Bayesian regularization for overall team strength

**Where This Analysis Is Lacking**
Honest, prominent section — not buried. Bullet list:
- ~15 teams have sparse or missing player data (Ghana, Cape Verde, Haiti, Bosnia, South Africa, Curaçao, New Zealand, Egypt, Iraq, Uzbekistan, and others) — model falls back to lower-confidence priors for these
- Squad announcements are still pending for some nations; full lineups will sharpen predictions
- International xG samples are inherently small (8–12 matches per cycle) — club aggregation compensates but can't fully replace tournament-level signal
- Page will be updated as final squads are confirmed

---

## Section: Results

### Layout — Three Subsections

**1. Tournament Winner**
A ranked table of all 48 teams by predicted tournament win probability (ensemble model). A **search/filter input** above the table lets users type a country name to narrow rows instantly (client-side, no server call). Columns:
- Rank
- Team name (with flag emoji or ISO code)
- Win%
- Reach semifinals%
- Exit in group stage%
- Data confidence: `HIGH` / `MEDIUM` / `LOW` (based on player data coverage)

Default sort: Win% descending. No other sort/filter UI needed.

**2. Stage-by-Stage Bracket**
Predicted winner at each knockout round, displayed as a visual bracket tree:
- Group winners (12 groups)
- Round of 32 (best-of-two per match)
- Round of 16
- Quarterfinals
- Semifinals
- **Final + predicted winner**

Each match shows two teams and a win probability split (e.g. `Brazil 67% vs France 33%`). Predicted winner side is highlighted.

**3. Model Agreement Signal** _(small callout — for statistician friends)_
Flag matches or outcomes where all three base models agree vs. where they diverge. No betting language — just note "models converge here" vs "models disagree — higher uncertainty."

---

## Hosting

- **Platform:** GitHub Pages
- **Deploy path:** `docs/` folder in this repo or a dedicated `gh-pages` branch
- **URL pattern:** `https://<username>.github.io/fulbol-mundial-26/`
- **Single file preferred:** `index.html` with inline or co-located CSS — keeps deployment trivial

---

## Data Pipeline

The report reads pre-computed outputs from `data/derived/` and `results/wc2026-sim/`. No live computation at render time. A small Python script (`tools/generate_report_data.py` or similar) exports the needed JSON from the parquet files for the HTML to consume.

### Data sources for the page
| Data needed | Source file |
|-------------|-------------|
| Win% per team (all models) | `data/derived/team_ratings_all_models.parquet` + sim results |
| Match predictions per round | `results/wc2026-sim/` |
| Data confidence per team | `None` aliases in `tools/simulate_wc2026.py` |

---

## Non-Goals

- No live data refresh / realtime updates (snapshot at publish time)
- No user login or personalization
- No mobile-first optimization (desktop-friendly is fine)
- No betting advice framing on the public page

---

## Success Criteria

- A statistician friend can read the methodology in under 3 minutes and understand the modeling approach
- Any friend can find their country and see its predicted path in under 30 seconds
- The page clearly communicates which predictions are low-confidence before readers over-index on them
- Deployment is a single `git push` away

---

## Open Questions (resolve during planning)

1. **Bracket rendering:** With 32 teams across 6 knockout rounds, a pure CSS bracket tree is brittle at this scale. Recommended: render rounds as **vertical columns of match cards** (flex layout) rather than a traditional bracket tree — simpler, scrollable, mobile-tolerant. Final decision at planning time.
2. Data export format: inline JSON in the HTML, or a `data.json` file fetched at load? Separate file is cleaner for updates.
3. Does the repo already have a GitHub Pages setup (`gh-pages` branch or `docs/` folder)?
