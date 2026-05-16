---
title: "feat: WC2026 Prediction Report — Static Web Page on GitHub Pages"
type: feat
status: completed
date: 2026-05-05
origin: docs/brainstorms/2026-05-05-wc2026-prediction-report-requirements.md
---

# feat: WC2026 Prediction Report — Static Web Page on GitHub Pages

## Overview

Build a shareable static web report at `docs/index.html`, served via GitHub Pages, presenting the WC2026 simulation model to friends and statistician colleagues. The page has two tabs — `METHODOLOGY` and `RESULTS` — styled with a dark terminal aesthetic (monospace font, near-black background, single accent color). A Python export script merges existing parquet/JSON outputs into a single `docs/data.json` that the page fetches at load time.

## Problem Frame

The model produces solid outputs (10k Monte Carlo runs across 4 models, 48-team probabilities, market comparisons) that currently live in parquet files. Friends and colleagues can't see any of it. A single-URL, no-login report fixes that. (see origin: `docs/brainstorms/2026-05-05-wc2026-prediction-report-requirements.md`)

## Requirements Trace

- R1. Shareable single URL hosted on GitHub Pages — no login, no backend
- R2. Two-tab layout: `METHODOLOGY` (how it works) and `RESULTS` (predictions)
- R3. Dark terminal aesthetic — monospace font, near-black background, one accent color
- R4. Methodology section: data sources, 4 models, simulation, feature weights, honest data gaps
- R5. Results: ranked 48-team win% table with search filter and confidence badges
- R6. Results: stage-by-stage bracket showing predicted winners at each knockout round with win probability splits
- R7. Model agreement signal for statistician audience (converge vs. diverge callout)
- R8. Page clearly flags ~14 low-confidence teams before readers over-index on their predictions
- R9. Re-publishing is a single `git push` away

## Scope Boundaries

- No live data refresh or server-side computation
- No mobile-first design (desktop-friendly sufficient)
- No user login or personalization
- No betting advice framing on the public page
- No JavaScript build tooling or frameworks — vanilla HTML/CSS/JS only

## Context & Research

### Relevant Code and Patterns

- `results/wc2026-sim/probabilities.json` — ready-made team probabilities: `{ "USA": { r32, r16, qf, sf, final, champion } }` all as decimals (0–1)
- `data/derived/team_ratings_all_models.parquet` — columns `nation, M1_History, M2_Season, M3_RecentForm` (48 rows, 0–1 scale)
- `data/raw/sofascore/understat_id_map.json` — may contain flag/country name lookup
- `tools/simulate_wc2026.py` lines 35–48 — the 14 `None`-alias teams that get fallback ratings (these become `"confidence": "LOW"`)
- `data/derived/kalshi_snapshot_2026-04-28.csv`, `polymarket_snapshot_2026-04-28.csv` — market odds for model-vs-market callout

### Institutional Learnings

- No existing frontend patterns in this repo — first HTML/CSS/JS in the codebase
- Data pipeline already exports `probabilities.json`; the new export script is additive, not a replacement

## Key Technical Decisions

- **Vanilla stack, no build step:** No npm, no bundler, no React. One HTML file + one CSS block + one JS block. Reduces deployment to `git push`. (see origin)
- **`docs/` folder on `main` for GitHub Pages:** Avoids a separate `gh-pages` branch; repo research confirmed `docs/` exists and GitHub Pages is not yet configured. Enable Pages under repo Settings → Pages → Source: `docs/` on `main`.
- **`docs/data.json` fetched at load:** Export script merges all sources into one JSON file co-located with index.html. Cleaner than inline JSON for future re-runs; `fetch('data.json')` works with GitHub Pages. (resolves open question 2)
- **Bracket display as round columns, not tree:** WC2026 has 12 groups + 6 knockout rounds (R32 → Final). A traditional bracket tree at this scale is fragile CSS. Render each round as a vertical column of match cards in flexbox. (resolves open question 1)
- **Confidence level from known `None` aliases:** The 14 teams with `None` in `simulate_wc2026.py` become `LOW`; teams with sparse-but-present ratings become `MEDIUM`; well-represented teams become `HIGH`. The export script encodes this as a static lookup.
- **Bracket derivation from probabilities:** The export script generates a predicted bracket by treating the highest-probability team per group as the group winner, then propagating expected matchups forward using WC2026 bracket seeding rules. This is a best-guess snapshot, not a full probabilistic trace.

## Open Questions

### Resolved During Planning

- **Bracket rendering approach:** Vertical round columns in flexbox — simpler, scrollable, avoids brittle CSS tree.
- **Data export format:** `docs/data.json` fetched at load — confirmed cleaner for re-publishing.
- **GitHub Pages setup:** `docs/` on `main` branch — not yet enabled; Unit 6 handles this.
- **Bracket data derivation:** Export script derives group winners + knockout path from probabilities.json using WC2026 bracket seeding order.

### Deferred to Implementation

- Exact flag emoji coverage per team (some ISO codes may not render uniformly; fallback to country name abbreviation)
- Precise seeding rules for best-third selection in R32 (implementation should match `simulate_wc2026.py` logic)
- Whether `MEDIUM` confidence threshold is `M2_Season < 0.5` or another cutoff — determine from rating distribution at implementation time

## Output Structure

    docs/
    ├── index.html          # page shell + all content + tab JS + render JS
    ├── style.css           # extracted CSS (optional — may stay inline for simplicity)
    └── data.json           # generated by tools/export_web_data.py

    tools/
    └── export_web_data.py  # merges parquet + JSON → docs/data.json

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
tools/export_web_data.py
  reads: results/wc2026-sim/probabilities.json
         data/derived/team_ratings_all_models.parquet
         data/derived/kalshi_snapshot_2026-04-28.csv
         data/derived/polymarket_snapshot_2026-04-28.csv
  derives: confidence level per team (HIGH/MEDIUM/LOW)
  derives: predicted bracket (group winners + KO progression)
  writes: docs/data.json

docs/index.html
  on load: fetch('data.json') → populate RESULTS tab
  tab toggle: show/hide #methodology and #results divs (JS + CSS)

  #methodology (static HTML, no data fetch)
    └── sections: Data Sources, Models, Simulation, Feature Weights, Data Gaps

  #results (JS-rendered from data.json)
    ├── search input → filters team table rows
    ├── #team-table (48 rows, sorted by champion%)
    │     columns: rank, flag+name, champion%, final%, semi%, group_exit%, confidence badge
    ├── #bracket (round columns in flexbox)
    │     columns: Groups (12), R32 (16 matches), R16 (8), QF (4), SF (2), Final (1)
    │     each match card: team1 [pct%] vs team2 [pct%] — winner highlighted
    └── #model-agreement (small section)
          lists matches where all 3 base models agree vs. diverge
```

## Implementation Units

- [ ] **Unit 1: Data export script**

**Goal:** Merge all model outputs into `docs/data.json` — single source of truth for the web page.

**Requirements:** R1, R5, R6, R7, R8, R9

**Dependencies:** None — all source files already exist

**Files:**
- Create: `tools/export_web_data.py`
- Create: `docs/data.json` (generated output, committed to repo)

**Approach:**
- Load `probabilities.json` as base — data lives at `d["probabilities"]`, not the root; 48 teams, 6 stage keys each (`r32`, `r16`, `qf`, `sf`, `final`, `champion`)
- Join with `team_ratings_all_models.parquet` on team name (normalize casing for join)
- Join with Kalshi snapshot — Kalshi uses ISO codes (`US`, `BR`, `BIH`), not full names; export script must include or build an ISO→canonical-name lookup map before joining. Known mismatches must be hardcoded (e.g., `BIH` → `Bosnia and Herzegovina`)
- Join with Polymarket snapshot — Polymarket uses variant spellings: `"Bosnia-Herzegovina"`, `"DRC"`, `"Turkiye"` etc.; export script must normalize these to canonical names before joining. Null market odds (no Polymarket entry) should be stored as `null`, not silently dropped
- Apply confidence classification: teams in the `None`-alias list → `LOW`; teams with `M2_Season` below a threshold or missing → `MEDIUM`; all others → `HIGH`
- Derive predicted bracket: sort teams by predicted group winner (highest `r32` within each group per WC2026 group assignments), then propagate the most-likely winner forward at each stage using the `champion` probability as tiebreaker
- Output shape: `{ meta, teams: [...], bracket: { groups, r32, r16, qf, sf, final, champion }, model_agreement: [...] }`
- Script should be runnable standalone: `python tools/export_web_data.py`

**Patterns to follow:**
- `tools/simulate_wc2026.py` for team name normalization and `None`-alias list (copy the list directly)
- `tools/build_2026_ratings.py` for parquet read + pandas merge pattern

**Test scenarios:**
- Happy path: script runs without error, `docs/data.json` is created, contains exactly 48 team entries
- Edge case: all 14 `LOW`-confidence teams appear in output with `"confidence": "LOW"`
- Edge case: at least one team has non-null Kalshi and Polymarket odds
- Integration: bracket `champion` field matches the team with the highest `champion` probability in the teams array
- Error path: missing source file raises a clear error message, not a silent empty output

**Verification:**
- `python tools/export_web_data.py` exits 0 and `docs/data.json` is ≤ 200 KB
- `jq '.teams | length' docs/data.json` returns 48
- `jq '.bracket.champion' docs/data.json` returns a non-null team name

---

- [ ] **Unit 2: Page shell, CSS design system, and tab navigation**

**Goal:** Working two-tab HTML skeleton with dark terminal aesthetic and tab toggle behavior.

**Requirements:** R2, R3

**Dependencies:** None (static, no data fetch yet)

**Files:**
- Create: `docs/index.html`

**Approach:**
- Single HTML file; CSS in a `<style>` block in `<head>` (inline for simplicity — no separate `.css` file needed)
- Google Fonts import for `Space Mono` (fallback: `monospace`) in `<head>`
- CSS custom properties: `--bg: #1a1a2e`, `--surface: #16213e`, `--accent: #00d4ff`, `--text: #e0e0e0`, `--muted: #8888aa`, `--low: #ff6b6b`, `--med: #ffb703`
- Two `<div>` panels (`#methodology`, `#results`) — only one visible at a time
- Tab bar: two buttons (`METHODOLOGY`, `RESULTS`). JS toggles `active` class and panel visibility
- Tab states: active = accent text + `2px` bottom border in accent; hover (inactive) = accent text only; transitions with `0.15s ease`
- Page header: title (e.g. `WC2026 // PREDICTION MODEL`), subtitle, last-updated date from `data.json` meta

**Test scenarios:**
- Happy path: clicking `RESULTS` tab shows `#results`, hides `#methodology`; clicking `METHODOLOGY` reverses
- Happy path: page loads with `METHODOLOGY` tab active by default
- Edge case: page renders correctly with `data.json` fetch pending (no layout shift or JS error before fetch resolves)
- Test expectation: no automated test needed for visual CSS states — verified manually in browser

**Verification:**
- Open `docs/index.html` locally (via `python -m http.server` in `docs/`) — both tabs toggle correctly, fonts load, accent color appears

---

- [ ] **Unit 3: Methodology tab — static content**

**Goal:** Write all methodology section content as static HTML inside `#methodology`.

**Requirements:** R4, R8

**Dependencies:** Unit 2 (page shell)

**Files:**
- Modify: `docs/index.html`

**Approach:**
- Five subsections rendered as styled `<section>` elements with `<h2>` and `<ul>` / `<p>` tags:
  1. **DATA SOURCES** — StatsBomb open data (WC22, Euro24, Copa24), Understat 2024-25 club xG, Kalshi/Polymarket market prices, 7,961 international results since 2018
  2. **MODELS** — four one-liners (ELO BASELINE, POISSON GOALS, LAST-10 FORM, ENSEMBLE) with monospace labels styled in accent color
  3. **SIMULATION** — 10,000 Monte Carlo runs, 12-group WC2026 structure, ET + penalty shootout modeling
  4. **FEATURE WEIGHTS** — club xG 60%, national team xG 40%, Elo prior for regularization
  5. **WHERE THIS ANALYSIS IS LACKING** — prominent, not buried. Lists the ~14 low-data-coverage teams by name, notes squad announcement gaps, and states the page will be updated as rosters confirm. Styled with a muted warning color to distinguish from the rest

- All content is hardcoded HTML — no data fetch required for this section
- Tone: confident but plain — one sentence per bullet, no jargon without a parenthetical explanation

**Test scenarios:**
- Test expectation: none — static content, no behavioral logic to test. Visual review confirms section order, font rendering, and warning styling on the data-gaps section.

**Verification:**
- Read through the methodology section in browser — all 5 subsections present, data gaps section visually distinct

---

- [ ] **Unit 4: Results tab — 48-team probability table with search**

**Goal:** JS-rendered ranked table of all 48 teams fetched from `data.json`, with live client-side search filter and confidence badges.

**Requirements:** R5, R8

**Dependencies:** Unit 1 (data.json), Unit 2 (page shell)

**Files:**
- Modify: `docs/index.html` (add JS render function and table HTML scaffold)

**Approach:**
- On tab activation (or page load if Results is default), `fetch('data.json')` → parse → render table
- Table columns: `#` (rank), `Team` (flag emoji + name), `Champion%`, `Final%`, `Semi%`, `Group exit%`, `Confidence`
- Confidence badge: `HIGH` in muted green, `MEDIUM` in amber, `LOW` in muted red — pill-shaped spans with small font
- Search input above table: `keyup` listener filters displayed rows by team name substring (case-insensitive, no debounce needed at 48 rows)
- Table rows sorted by `champion%` descending (fixed — no interactive sort needed)
- Row hover: `rgba(255,255,255,0.04)` background tint via CSS `:hover`
- Percentages displayed as `18.3%` (multiply decimal × 100, one decimal place)

**Patterns to follow:**
- No framework — pure DOM manipulation (`document.createElement`, `innerHTML`, `classList`)
- Keep the render function under ~60 lines; readable over clever

**Test scenarios:**
- Happy path: all 48 teams render in the table after `data.json` loads
- Happy path: typing "bra" in the search box shows only Brazil (and any other team name containing "bra")
- Edge case: search with no match shows an empty table body with no JS error
- Edge case: clearing the search input restores all 48 rows
- Error path: if `fetch('data.json')` fails (e.g., CORS in direct file open), show an inline error message rather than a blank panel

**Verification:**
- `python -m http.server 8080` in `docs/` → open `localhost:8080` → Results tab shows 48 rows, search filters correctly, badges render in correct colors

---

- [ ] **Unit 5: Results tab — stage-by-stage bracket display**

**Goal:** Visual representation of the predicted knockout bracket from group stage through the Final, using round columns in flexbox.

**Requirements:** R6, R7

**Dependencies:** Unit 1 (bracket data in data.json), Unit 4 (data already fetched)

**Files:**
- Modify: `docs/index.html`

**Approach:**
- Section below the team table, headed `PREDICTED BRACKET`
- Layout: horizontal flexbox of round columns — `Groups`, `R32`, `R16`, `QF`, `SF`, `Final`
- Each column contains match cards; a match card shows:
  - Team 1 name (flag + abbreviated name)
  - Win probability split (e.g., `67% | 33%`)
  - Team 2 name
  - The predicted winner's row is highlighted with accent color text
- Groups column: 12 group winner cards (just the predicted winner per group — not full group standings)
- R32 through Final: match cards populated from `data.json bracket.r32 / .r16 / .qf / .sf / .final`
- Columns are horizontally scrollable on narrow viewports (no mobile breakpoint needed — `overflow-x: auto` on the container)
- Below the bracket, a small `MODEL AGREEMENT` callout: a compact list of the matches/outcomes where all 3 base models converge vs. diverge (from `data.json model_agreement`). Headed with a brief explainer: "Models agree → higher confidence. Models diverge → wider uncertainty."
- No animation or transitions beyond the existing tab toggle

**Patterns to follow:**
- Same `renderFromData()` pattern established in Unit 4 — extend the same fetch callback, don't add a second fetch

**Test scenarios:**
- Happy path: bracket renders 6 columns, Final column shows exactly 1 match card
- Happy path: the `champion` team's card in the Final column is highlighted in accent color
- Edge case: teams with `LOW` confidence appearing in the bracket display a `LOW` badge on their card
- Integration: the team named in `bracket.champion` matches the #1 row in the team probability table (same data source, no mismatch)
- Error path: if `bracket` key is missing from `data.json`, bracket section shows a "bracket data unavailable" message rather than a blank or JS error

**Verification:**
- In browser: bracket renders 6 columns, scrolls horizontally if needed, Final card names a champion that matches the top of the team table

---

- [ ] **Unit 6: GitHub Pages configuration and deployment**

**Goal:** Enable GitHub Pages from `docs/` on `main` so the report is reachable at a public URL.

**Requirements:** R1, R9

**Dependencies:** Units 1–5 (at least `docs/index.html` and `docs/data.json` committed)

**Files:**
- No file to create — this is a GitHub repo setting change

**Approach:**
- In the repo settings (GitHub web UI): Settings → Pages → Source → `Deploy from a branch` → Branch: `main`, Folder: `/docs`
- Commit and push `docs/index.html` + `docs/data.json` to `main`
- GitHub Actions will deploy automatically; URL will be `https://<username>.github.io/fulbol-mundial-26/`
- Add a one-liner to the repo `README.md` with the live URL once confirmed

**Test scenarios:**
- Happy path: visiting the GitHub Pages URL loads `index.html` and `data.json` fetches successfully (no CORS issue — same origin)
- Happy path: tab navigation and search work identically to local `http.server` test
- Error path: if the URL returns a 404, verify `docs/` folder is on `main` and Pages source is set correctly

**Verification:**
- Public URL loads, both tabs render, team table shows 48 rows

---

## System-Wide Impact

- **Interaction graph:** Export script reads from `results/wc2026-sim/probabilities.json` and `data/derived/` parquets — no writes back to those files
- **Error propagation:** Export script failures are local — they don't affect the simulator or ratings pipeline
- **State lifecycle risks:** `docs/data.json` is committed to `main`; re-running export + committing is the update mechanism. Old data persists until re-committed
- **Unchanged invariants:** `tools/simulate_wc2026.py` and all rating scripts are untouched — export script is read-only consumer
- **Integration coverage:** The `fetch('data.json')` call works on GitHub Pages (same-origin) but will fail with a CORS error when opening `index.html` directly from the filesystem. Testers must use `python -m http.server` locally.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `probabilities.json` is two-level: all team data is under `d["probabilities"]`, not the root | Export script must access `data["probabilities"]` — not `data` directly. Add an assertion that `len(data["probabilities"]) == 48` |
| Kalshi uses ISO codes (`US`, `BR`, `BIH`) — no direct join to full team names | Export script includes a hardcoded ISO→canonical-name map. Known outliers: `BIH`→`Bosnia and Herzegovina`, `CUW`→`Curaçao`, `NZL`→`New Zealand` |
| Polymarket uses variant spellings (`Bosnia-Herzegovina`, `DRC`, `Turkiye`) | Export script normalizes Polymarket `outcome` column before joining; null market odds stored as `null` in output, not dropped |
| Team name normalization mismatch between probabilities.json and parquet | Normalize to lowercase + strip accents in export script; add assertion that join result has 48 rows |
| 14 `None`-alias teams missing from `team_ratings_all_models.parquet` | Export script hardcodes `LOW` confidence for the known alias list; no join required for these |
| WC2026 bracket seeding rules are complex for best-thirds | Simplify: show most likely teams at each stage from probability ranking; note in UI that bracket is "model-predicted path, not official seeding" |
| Flag emoji rendering varies across OS/browser | Fallback to ISO country code (e.g., `BRA`) if emoji is unsupported; CSS `font-family` fallback to system emoji font |
| GitHub Pages deployment delay (2–5 min after push) | Expected behavior — no mitigation needed |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-05-wc2026-prediction-report-requirements.md](docs/brainstorms/2026-05-05-wc2026-prediction-report-requirements.md)
- Related code: `tools/simulate_wc2026.py` (None-alias list, lines 35–48)
- Related code: `results/wc2026-sim/probabilities.json` (primary data feed)
- Related code: `data/derived/team_ratings_all_models.parquet` (model rating columns)
