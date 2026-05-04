---
title: "feat: 2026-only player data pipeline via Sofascore"
type: feat
status: active
date: 2026-05-04
---

# feat: 2026-only player data pipeline via Sofascore

## Overview

Pull **only 2026 match data** for every confirmed WC2026 squad player from Sofascore. Compute each player's 2026 xG/90, shots/90, goals/90, and minutes played this year. Use this as the primary rating signal for the simulation — replacing the stale 2022-2024 StatsBomb and Understat data.

**Why 2026 only:** A player's January-May 2026 form is the most direct proxy for their World Cup performance. Historical data from 2022-2024 is noise compared to what they've done in the past 4 months.

**Deadline:** Must be runnable by June 1, 2026 once final squads are confirmed.

## What We Confirmed Works

Tested against Mbappé (Sofascore player ID 826643):
- `api.sofascore.com/api/v1/player/{id}/events/last/0` → 20 matches in 2026 returned
- `api.sofascore.com/api/v1/event/{match_id}/player/{player_id}/statistics` → xG available for major leagues (LaLiga, UCL, Bundesliga, etc.)
- Sample 2026 data: Jan 17 LaLiga xG=1.39, Jan 20 UCL xG=1.11, Jan 24 LaLiga xG=1.18
- xG is absent for cup competitions (Supercopa) — fall back to shots in those cases
- No auth required — browser headers sufficient

## Requirements Trace

- R1. Pull official WC2026 squad lists (26 players per nation, 48 nations)
- R2. For every squad player, find their Sofascore player ID
- R3. Pull all matches played since Jan 1, 2026 per player
- R4. Extract per-match: `expectedGoals`, `totalShots`, `goals`, `minutesPlayed`
- R5. Aggregate to 2026 xG/90 per player (minimum 90 total minutes to be reliable)
- R6. Rebuild `team_attack_ratings.parquet` from 2026 data only
- R7. All scripts idempotent — safe to re-run as squads update

## Scope Boundaries

- **2026 only** — no 2022, 2023, 2024 data. Fresh signal only.
- No Understat, no StatsBomb for this pipeline — Sofascore is the single source
- Squad lists pulled once when confirmed (~May 28-June 1) — no live roster tracking
- No defensive ratings in this plan — attack proxy only, same as current model
- 48 WC nations only, not all world football

## Key Technical Decisions

- **Sofascore as sole 2026 source** — confirmed accessible, has xG for major leagues and Champions League, covers all 48 WC nations regardless of league
- **xG fallback to shots** — when `expectedGoals` is null (cup competitions, some smaller leagues), use `totalShots × 0.1` as a conservative proxy (average xG per shot ≈ 0.1)
- **Minimum 90 minutes in 2026** — same guard as the Sarabia fix: players with < 90 total minutes in 2026 get no rating from this pipeline (prevents small-sample explosions)
- **Player ID discovery via search** — `api.sofascore.com/api/v1/search/players?q={name}`, pick the result matching the known squad nationality
- **Cache per player** — `data/raw/sofascore/players/{player_id}_2026.json` stores raw match array. Idempotent: skip if file < 7 days old
- **Squad list source: Wikipedia** — national squad pages update within hours of official announcements, scrapable without auth

## Timeline

| Date | Milestone |
|------|-----------|
| May 4 | Build squad puller + Sofascore scripts |
| May 20 | Begin running squad puller daily |
| ~May 29 | FIFA official squad deadline |
| Jun 1 | Run full Sofascore pull for all confirmed squads |
| Jun 5 | Rebuild ratings, re-run simulation |
| Jun 11 | Tournament starts |

## Output Structure

```
data/raw/squads/
  wc2026_squads_confirmed.json    # {nation: [{name, position, club, sofascore_id}, ...]}

data/raw/sofascore/
  players/
    {player_id}_2026.json         # raw match array from Jan 1 2026 onward

data/derived/
  sofascore_2026_player_xg.parquet  # {player_id, name, nation, xg_per_90, shots_per_90, goals_per_90, minutes_2026, matches_2026}
  team_attack_ratings.parquet       # rebuilt from 2026 data
```

## Implementation Units

- [ ] **Unit 1: WC2026 squad list puller**

**Goal:** Scrape Wikipedia for official 26-player WC2026 rosters. Run daily from May 20 until all 48 nations confirmed. Stores player name, position, club, and country per nation.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Create: `tools/pull_wc2026_final_squads.py`
- Create/update: `data/raw/squads/wc2026_squads_confirmed.json`

**Approach:**
- URL pattern: `https://en.wikipedia.org/wiki/{Nation}_at_the_2026_FIFA_World_Cup`
- Parse the squad table: player name, position (GK/DF/MF/FW), club
- If page 404s or has no squad table yet → log `[pending]` and continue
- Output JSON: `{"France": [{"name": "K. Mbappé", "position": "FW", "club": "Real Madrid"}, ...], "pending": ["Curaçao", ...]}`
- Print: `N/48 nations confirmed`
- Run daily — idempotent (overwrites file each run with latest state)

**Patterns to follow:**
- `tools/pull_wc2026_squads.py` — existing Wikipedia HTML scraper pattern
- `tools/pull_statsbomb.py` — json.dumps(indent=2) write pattern

**Test scenarios:**
- Post-announcement: France page returns 26 players with name + position
- Pre-announcement: page exists but no squad table yet → `[pending]`, no crash
- Full run: script completes across all 48 nations without crashing on missing pages
- Idempotency: running twice overwrites file, no duplicate players

**Verification:**
- `python3 -c "import json; d=json.load(open('data/raw/squads/wc2026_squads_confirmed.json')); print(len(d)-1, 'nations, pending:', d.get('pending',[]))"` (subtract 1 for the `pending` key)
- At least one confirmed nation has exactly 26 players

---

- [ ] **Unit 2: Sofascore player ID resolver**

**Goal:** For every player in the confirmed squad lists, find their Sofascore player ID. Stores name → ID mapping as a lookup file.

**Requirements:** R2

**Dependencies:** Unit 1

**Files:**
- Create: `tools/resolve_sofascore_ids.py`
- Create: `data/raw/sofascore/player_id_map.json`  — `{"K. Mbappé": 826643, ...}`

**Approach:**
- Load `wc2026_squads_confirmed.json`
- For each player not already in `player_id_map.json`: search `api.sofascore.com/api/v1/search/players?q={name}`
- From results, pick the entity whose nationality matches the squad's nation (use `team.national` flag and country name)
- If multiple hits and no clear nationality match, pick highest `userCount` (more popular = more likely correct)
- If no result found, log `[not found: {name}]` — player stays unmapped (will use team fallback)
- Rate limit: `time.sleep(0.5)` between searches
- Idempotent: skip players already in the map

**Patterns to follow:**
- `tools/fetch_match_events.py` — browser headers, urllib pattern
- `tools/pull_statsbomb.py` — cache-before-fetch

**Test scenarios:**
- Happy path: "Kylian Mbappé" → 826643, nationality France confirmed
- Name mismatch: "K. Mbappé" (abbreviated) still finds correct player via search
- Not found: obscure player from Curaçao returns empty → logged, not crashed
- Idempotency: second run skips all already-resolved players

**Verification:**
- `python3 -c "import json; m=json.load(open('data/raw/sofascore/player_id_map.json')); print(len(m), 'players resolved')"` — expect 900+ for 48 nations × ~26 players minus not-founds
- Spot check: `map["Kylian Mbappé"] == 826643`

---

- [ ] **Unit 3: Pull 2026 match stats per player**

**Goal:** For every resolved player, pull all matches played since Jan 1, 2026 from Sofascore and fetch per-match xG, shots, goals, and minutes. Save raw cache per player.

**Requirements:** R3, R4, R7

**Dependencies:** Unit 2

**Files:**
- Create: `tools/pull_sofascore_2026_stats.py`
- Create: `data/raw/sofascore/players/{player_id}_2026.json` per player

**Approach:**
- Load `player_id_map.json`; for each player:
  - If cache file exists and is < 7 days old → skip (use cached)
  - Fetch: `api.sofascore.com/api/v1/player/{id}/events/last/0` (returns ~30 recent events)
  - Filter to events where `startTimestamp >= 1735689600` (Jan 1, 2026 UTC)
  - For each 2026 match, fetch: `api.sofascore.com/api/v1/event/{match_id}/player/{player_id}/statistics`
  - Extract: `expectedGoals` (or `totalShots × 0.1` if null), `totalShots`, `goals`, `minutesPlayed`
  - Save all matches as array in `{player_id}_2026.json`
  - Rate limit: `time.sleep(0.4)` between player fetches
- Print progress: `[ok] Mbappé: 20 matches, 847 mins, 14.2 xG`

**Technical design:** *(directional)*
```
player_id_map.json
  ↓ for each player_id
  GET /player/{id}/events/last/0
    → filter startTimestamp >= Jan 1 2026
    → for each match_id
      GET /event/{match_id}/player/{player_id}/statistics
        → extract {xg, shots, goals, minutes}
  → save [{match_id, date, xg, shots, goals, minutes}, ...] to {player_id}_2026.json
```

**Patterns to follow:**
- `tools/fetch_match_events.py` — urllib with browser headers, file-exists idempotency
- `tools/pull_statsbomb.py` — `json.dumps(indent=2)`, skip-if-exists

**Test scenarios:**
- Happy path: Mbappé gets 20 matches with valid xG/shots/minutes
- No xG (cup match): `expectedGoals` null → falls back to `totalShots × 0.1`
- Zero minutes (non-playing squad member): match included with 0 minutes, filtered at aggregation step
- Network error mid-run: partially-cached players are safe; restart skips them
- Idempotency: second run skips all players with recent cache files

**Verification:**
- `ls data/raw/sofascore/players/ | wc -l` — expect ~900-1100 files
- `python3 -c "import json; d=json.load(open('data/raw/sofascore/players/826643_2026.json')); print(len(d), 'matches, total xG:', sum(m['xg'] for m in d))"` — expect ~20 matches, xG > 10
- No file contains `expectedGoals` values above 6.0 (physical ceiling)

---

- [ ] **Unit 4: Aggregate to 2026 player ratings and rebuild team ratings**

**Goal:** Read all player cache files, aggregate to 2026 xG/90 per player, join with squad lists, rebuild `team_attack_ratings.parquet` using only 2026 data.

**Requirements:** R5, R6

**Dependencies:** Units 1, 2, 3

**Files:**
- Create: `tools/build_2026_ratings.py`
- Create: `data/derived/sofascore_2026_player_xg.parquet`
- Rebuild: `data/derived/team_attack_ratings.parquet`

**Approach:**
- For each player in `player_id_map.json`:
  - Load `{player_id}_2026.json`
  - Sum: `total_xg`, `total_shots`, `total_goals`, `total_minutes`
  - If `total_minutes < 90` → flag as unreliable, assign `xg_per_90 = None`
  - Else: `xg_per_90 = total_xg / (total_minutes / 90)`
  - Cap: if `xg_per_90 > 6.0` → flag unreliable (Sarabia rule)
- Save `sofascore_2026_player_xg.parquet` with one row per player
- For each nation, take the **top 5 players by xg_per_90** (reliable only) and average → `attack_rating`
- If nation has < 3 reliable players → use 25th-percentile fallback
- Save updated `team_attack_ratings.parquet`
- Print ranked table: nation, attack_rating, players_with_2026_data, total_minutes

**Patterns to follow:**
- `tools/build_squad_xg_ratings.py` — team aggregation pattern, MIN_MINUTES guard, MAX_XG90 guard

**Test scenarios:**
- Happy path: France, Spain, Argentina all have 10+ reliable players, attack_rating computed from 2026 data
- Minimum coverage: Curaçao might have only 2 reliable players → falls back to 25th-percentile
- Sarabia rule: any player with xg_per_90 > 6.0 is flagged and excluded
- Minimum minutes: player with 45 total 2026 minutes excluded from rating
- Re-run simulation: `python3 tools/simulate_wc2026.py --n 1000 --seed 42` completes using new ratings

**Verification:**
- `python3 -c "import pandas as pd; df=pd.read_parquet('data/derived/team_attack_ratings.parquet'); print(df[['nation','attack_rating']].sort_values('attack_rating',ascending=False).head(10).to_string())"`
- Top 10 nations are defensible (France, Spain, Argentina, Brazil, Germany, Portugal-range)
- No nation has `attack_rating > 2.0` (old Spain bug)
- Nations previously on fallback (Norway, Ivory Coast) now have non-fallback ratings if players found
- `simulate_wc2026.py` runs to completion

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Sofascore blocks requests from repeated calls | `time.sleep(0.4)` between requests; cache aggressively; if blocked, run in batches across days |
| Player search returns wrong person (name collision) | Cross-check nationality from search result; prefer results with `national=True` team matching the squad nation |
| Many players have < 90 minutes in 2026 (bench players, injured) | Use team's available rated players; if < 3 reliable players, use fallback — don't force a bad rating |
| Wikipedia squad pages not up by June 1 | Manual JSON fallback: hardcode the 5-6 missing nations' squads from official federation announcements |
| xG absent for most matches in some leagues (Liga MX, Saudi Pro League) | Use shots-based proxy (`shots × 0.1`); it's noisier but still directional |
| Squad lists change after initial pull (late injuries/withdrawals) | Script is idempotent — re-run June 8-10 to capture final updates before Jun 11 kickoff |

## Sources & References

- Sofascore API: confirmed via `tools/fetch_match_events.py` browser-header pattern
- Sofascore player endpoint: `api.sofascore.com/api/v1/player/{id}/events/last/0` — tested, returns 30 events
- Sofascore stats endpoint: `api.sofascore.com/api/v1/event/{id}/player/{pid}/statistics` — tested, xG field confirmed for LaLiga/UCL
- Squad Wikipedia pattern: `tools/pull_wc2026_squads.py`
- MIN_MINUTES / MAX_XG90 guards: `tools/build_squad_xg_ratings.py`
- Current ratings for comparison: `data/derived/team_attack_ratings.parquet`
