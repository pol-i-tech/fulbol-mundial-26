---
title: "Player Data Gap Plan"
type: feat
status: active
date: 2026-05-06
---

# Player Data Gap Plan

Date: 2026-05-06

This plan keeps player-data work focused on improving model reliability. The project already has useful player signals, but coverage and freshness are uneven enough that wiring them directly into bet sizing would create false precision.

For the broader acquisition strategy covering the largest possible World Cup player universe, see `docs/plans/2026-05-06-world-cup-player-data-acquisition-strategy.md`.

## Current Assets

| File | Use | Limitation |
|---|---|---|
| `data/derived/sb_player_summary.parquet` | National-team event/xG history from StatsBomb tournaments | Tournament-only sample; misses many WC2026 players |
| `data/derived/understat_player_xg_raw.parquet` | Club xG and xA from recent club seasons | Mostly top leagues; not all national-team players covered |
| `data/derived/squad_xg_ratings.parquet` | Fuzzy joined player-level national + club signal | Name matching can be wrong or missing; not a confirmed WC2026 squad |
| `data/derived/team_attack_ratings.parquet` | Team-level top-player attack and pressing proxy | Attack-only proxy; no explicit defense, goalkeeper, or availability model |

## Non-Goals

- Do not re-attempt FBref scraping while the project guide marks FBref as Cloudflare-blocked.
- Do not add a dashboard to inspect players until a command-line coverage report exists.
- Do not manually boost teams or players inside model code without a documented parameter and backtest.
- Do not treat likely squads as confirmed squads.

## Required Guardrails

Every player-derived model must define:

- Missing-player fallback by position.
- Minimum minutes threshold for club data.
- Maximum age of club data before confidence is downgraded.
- Name-match override process.
- Injury/suspension handling policy.
- Backtest showing that the player signal helps calibration or a known blind spot.

## Implementation Plan

1. Add `tools/audit_player_coverage.py`.
   - Input: `squad_xg_ratings.parquet`, `team_attack_ratings.parquet`.
   - Output: `data/derived/player_coverage_report.csv`.
   - Columns: nation, players, matched_to_club, match_rate, national_minutes, low_minutes_players, missing_club_players, stale_players.

2. Add explicit name overrides.
   - Preferred file: `data/derived/player_name_overrides.csv`.
   - Columns: source_name, canonical_name, nation, understat_player_id, reason.
   - `build_squad_xg_ratings.py` should apply overrides before fuzzy matching.

3. Replace silent fallback behavior.
   - Current behavior uses national xG when club xG is missing.
   - New behavior should record `fallback_method` and `player_data_confidence`.
   - Team aggregation should weight low-confidence players less.

4. Separate player pool from squad assumption.
   - Add a `squad_status` field: `historical_pool`, `likely`, `confirmed`, `excluded`.
   - Until official squad data is reliable, model outputs should say they assume historical/likely pools.

5. Backtest player signal before production use.
   - WC2022: train on pre-WC2022 player data only.
   - Euro2024/Copa2024: use tournament-specific walk-forward windows.
   - Acceptance bar: improve log-loss or ECE versus the existing ensemble, or explain a specific class of misses without worsening calibration.

## Immediate Club-Level Track: Recent UCL Matches

Use recent UEFA Champions League knockout matches as high-signal club-form inputs for likely World Cup players. This is not a full player universe; it is a weekly "elite-club exposure" layer that can be joined later to national-team candidates.

### This week's target matches

For the week of 2026-05-05:

| Date | Competition | Match | Result | Source priority |
|---|---|---|---|---|
| 2026-05-05 | UCL semi-final second leg | Arsenal vs Atletico Madrid | Arsenal 1-0 Atletico Madrid; Arsenal advanced 2-1 aggregate | UEFA fixture page, Sky Sports teams page |
| 2026-05-06 | UCL semi-final second leg | Bayern Munich vs Paris Saint-Germain | Bayern 1-1 PSG; PSG advanced 6-5 aggregate | UEFA fixture page, Sky Sports teams page |

### Data to capture

For every player listed in these match squads:

| Field | Description |
|---|---|
| `match_id` | Stable source-specific match ID when available; otherwise `UCL-YYYY-MM-DD-HOME-AWAY` |
| `match_date` | ISO date |
| `competition` | `UEFA Champions League` |
| `stage` | e.g. `semi-final second leg` |
| `club` | Club name |
| `opponent` | Opponent club |
| `player` | Source display name |
| `shirt_number` | If available |
| `starter` | Boolean |
| `substitute` | Boolean |
| `sub_on_minute` | Minute entered, if any |
| `sub_off_minute` | Minute exited, if any |
| `minutes_played` | Estimated from start/substitution data; account for stoppage as capped match minute |
| `goals` | Count from match report |
| `assists` | Count if available |
| `yellow_cards` | Count |
| `red_cards` | Count |
| `source_url` | Exact source used |
| `source_confidence` | `official`, `verified_media`, or `derived` |

### Source order

1. UEFA match centre / tactical lineups / full-time report when accessible.
2. Sky Sports teams page for lineups, substitutes, substitutions, goals, and cards.
3. Club official match report if it includes lineups/minutes.
4. RotoWire or similar lineup pages only as fallback for confirmed starters/injury flags.

### Outputs

Write two derived files:

- `data/derived/ucl_recent_player_minutes.csv`
- `data/derived/ucl_recent_match_squads.csv`

The first is player-match grain. The second is match-squad grain and should preserve bench players who did not appear.

### Later join to World Cup candidates

Once WC squads are clearer:

1. Join UCL player rows to `squad_xg_ratings.parquet` by explicit override, then fuzzy name.
2. Add nationality from club/player source only when reliable.
3. Compute:
   - `ucl_minutes_last_30d`
   - `ucl_starts_last_30d`
   - `ucl_goal_contributions_last_30d`
   - `elite_club_recent_form_flag`
4. Use this as a confidence/availability signal, not as a direct team boost until backtested.

## Review Checklist

- Does coverage improve for weaker/non-European squads, or only for already well-covered elite teams?
- Are unmatched high-impact players visible in a report?
- Are manual overrides auditable?
- Does missing data lower confidence instead of creating fake certainty?
- Did validation improve out of sample?
