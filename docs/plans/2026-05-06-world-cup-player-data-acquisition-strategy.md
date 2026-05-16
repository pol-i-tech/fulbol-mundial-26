---
title: "World Cup Player Data Acquisition Strategy"
type: feat
status: active
date: 2026-05-06
---

# World Cup Player Data Acquisition Strategy

Date: 2026-05-06

Goal: build the largest reliable player dataset possible for the 2026 World Cup without drifting into brittle scraping or undocumented manual adjustments.

The strategy is to build a **player candidate universe first**, then attach national-team usage, club minutes, and advanced stats in separate layers. We should not wait for final squads before collecting data, but final squads become the authority once FIFA publishes them.

## Known Squad Timing

FIFA says 2026 squads allow 26 players per team. Participating associations provide preliminary lists of 35-55 players, and final-squad replacements can only come from the provisional list except under FIFA's injury/illness rules. FIFA also states the release/rest period begins on 2026-05-25, with exceptions for players in confederation club finals through 2026-05-30.

Implication: until final squads are published, the best player universe is:

1. Official preliminary squads when available.
2. Recent national-team callups and match squads.
3. Recent club minutes for players likely to be called.

## Data Layers

### Layer 1: Player Registry

This is the canonical identity table. Every downstream file joins through this table.

Output: `data/derived/player_registry.parquet` and `.csv`

Required fields:

| Field | Description |
|---|---|
| `player_id` | Project-generated stable ID |
| `canonical_name` | Project canonical name |
| `name_variants` | Pipe-separated aliases from sources |
| `date_of_birth` | If available |
| `primary_national_team` | FIFA 3-letter code |
| `eligible_national_teams` | If ambiguous |
| `current_club` | Latest known club |
| `position_group` | GK / DEF / MID / FWD |
| `source_ids` | JSON or pipe-separated source IDs |
| `identity_confidence` | high / medium / low |

Rules:

- Do not use display name alone as an identifier.
- Prefer source IDs, date of birth, nationality, club, and position for matching.
- Any manual mapping must live in `data/derived/player_name_overrides.csv`, not inside model code.

### Layer 2: World Cup Candidate Pool

This is the broad list of players who might go to the World Cup.

Output: `data/derived/wc2026_player_candidates.parquet` and `.csv`

Candidate sources, in priority order:

| Priority | Source | Use |
|---:|---|---|
| 1 | FIFA official final squad lists | Final authority once published |
| 2 | FIFA official preliminary squad lists | Main pool before final squads |
| 3 | National federation squad announcements | Recent callups and camp lists |
| 4 | Match squads from recent internationals | Players actually selected recently |
| 5 | Starting lineups/subs from recent internationals | Recent usage and likely-role signal |
| 6 | Club-level elite competition participation | Form/fitness signal for candidates |

Candidate fields:

| Field | Description |
|---|---|
| `player_id` | Join to registry |
| `team_code` | FIFA 3-letter team |
| `squad_status` | `candidate`, `recent_callup`, `preliminary`, `confirmed`, `excluded` |
| `evidence_source` | URL or source file |
| `evidence_date` | Date evidence was observed |
| `candidate_confidence` | high / medium / low |

### Layer 3: National-Team Recent Usage

This tells us who national teams actually use.

Output: `data/derived/national_recent_player_minutes.parquet` and `.csv`

Source order:

1. FIFA Match Centre for World Cup and qualifying match data.
2. Confederation match reports and tactical lineups.
3. Federation match reports.
4. Verified media lineup pages only when official data is missing.
5. Paid API fallback only if it improves coverage materially.

Fields:

| Field | Description |
|---|---|
| `match_id` | Stable match ID |
| `match_date` | ISO date |
| `team_code` | National team |
| `opponent_code` | Opponent |
| `competition` | Qualifier, friendly, Nations League, etc. |
| `player_id` | Join to registry |
| `starter` | Boolean |
| `bench` | Boolean |
| `sub_on_minute` | If any |
| `sub_off_minute` | If any |
| `minutes_played` | Estimated or official |
| `source_url` | Source |
| `source_confidence` | official / verified_media / derived |

Derived features:

- `national_minutes_last_5`
- `national_minutes_last_10`
- `national_starts_last_5`
- `national_squad_appearances_last_10`
- `last_national_appearance_date`

### Layer 4: Club-Level Recent Form and Minutes

This captures player fitness and current role at club level.

Outputs:

- `data/derived/club_recent_player_minutes.parquet`
- `data/derived/club_player_season_stats.parquet`
- `data/derived/ucl_recent_player_minutes.csv` for immediate UCL pulls

Source order:

| Priority | Source | Use |
|---:|---|---|
| 1 | Existing Understat data | Club xG/xA for covered leagues |
| 2 | UEFA match reports / tactical lineups | UCL/UEL/UECL recent minutes and event context |
| 3 | API-FOOTBALL or SportMonks evaluation | Broader lineups/player stats across many leagues |
| 4 | football-data.org | Competition/team/player metadata if coverage is enough |
| 5 | Verified media lineups | Backup for individual high-priority matches |

Evaluation rule for paid APIs:

- Do a small trial for 10-20 candidate players across different regions.
- Check identity reliability, club-season stats, lineups, substitutions, and rate limits.
- Adopt only if it closes measurable gaps for non-European and smaller-league players.

Club fields:

| Field | Description |
|---|---|
| `player_id` | Join to registry |
| `club` | Club at match date |
| `competition` | League/cup |
| `match_date` | ISO date |
| `starter` | Boolean |
| `minutes_played` | Match minutes |
| `goals` | Match goals |
| `assists` | Match assists |
| `xg` | If available |
| `xa` | If available |
| `shots` | If available |
| `key_passes` | If available |
| `source_url` | Source |
| `source_confidence` | official / api / verified_media / derived |

Derived features:

- `club_minutes_last_30d`
- `club_minutes_last_60d`
- `club_starts_last_30d`
- `club_xg90_current_season`
- `club_xa90_current_season`
- `club_data_freshness_days`
- `elite_comp_minutes_last_30d`

## Coverage Targets

After final squads:

| Coverage item | Target |
|---|---:|
| Basic identity for final-squad players | 100% |
| Current club and position group | 95%+ |
| Recent national-team minutes | 85%+ |
| Recent club minutes | 85%+ |
| Club attacking stats for attackers/mids | 70%+ |
| xG/xA or equivalent advanced stats | 60%+ overall, higher for top leagues |
| Manual identity overrides audited | 100% |

Before final squads:

| Coverage item | Target |
|---|---:|
| Candidate pool per qualified team | 35-55 players where possible |
| Recent callup coverage | 80%+ of likely squad |
| Club minutes for candidate attackers/mids | 70%+ |

## Quality Gates

Player data cannot influence production probabilities until these pass:

1. `player_registry` has no duplicate high-confidence identities.
2. Every manual override has a reason and source.
3. Missing club data creates a fallback label and lowers confidence.
4. Player signals improve a held-out tournament metric or explain a documented blind spot without hurting calibration.
5. Coverage is reported by team, confederation, and position group.

## Source Policy

Allowed:

- Official FIFA/confederation/federation reports.
- Existing committed StatsBomb and Understat-derived data.
- UEFA match reports and tactical lineups.
- Paid APIs after a scoped evaluation.
- Verified media pages as fallback with source labeling.

Avoid:

- FBref, while `DEVELOPMENT.md` marks it as Cloudflare-blocked.
- Automated scraping of sites whose terms or bot protections make reuse brittle.
- Manual player boosts inside model code.
- Treating Wikipedia or unsourced roster pages as final authority when official FIFA squad lists exist.

## Work Plan

1. Build `tools/build_player_registry.py`.
2. Build `tools/audit_player_coverage.py`.
3. Add `data/derived/player_name_overrides.csv`.
4. Build `tools/pull_recent_national_lineups.py`.
5. Build `tools/pull_ucl_recent_player_minutes.py` for elite club recency.
6. Evaluate one paid API for global club coverage.
7. Join all layers into `data/derived/wc2026_player_model_inputs.parquet`.
8. Backtest the player layer before using it in `weekly_pull.py` or any betting comparison.

## Minimum Useful Version

The smallest useful version is:

- `player_registry`
- `wc2026_player_candidates`
- `national_recent_player_minutes`
- `club_recent_player_minutes`
- `player_coverage_report`

That gives the model enough information to know who is likely relevant, who is actually playing, and where data is missing.
