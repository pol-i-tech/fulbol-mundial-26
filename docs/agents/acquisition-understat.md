# Acquisition: Understat club xG

## Mission

Pull club-level player xG and xA from Understat for the top 5 European leagues plus the Russian Premier League, across the most recent 3 seasons (currently 2022, 2023, 2024). Club xG is the project's main signal for *current player form* — the StatsBomb data is national-team only and dated; Understat tells us who is playing well right now.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Understat | `https://understat.com/league/<league>/<year>` | Public; no auth; pages embed JSON in script tags |
| Leagues | EPL, La_liga, Bundesliga, Serie_A, Ligue_1, RFPL | Fixed in `tools/pull_understat_players.py` |

Rate limit: Understat tolerates polite scraping. The puller throttles per-league.

## Outputs

| Output | Path | Schema |
|---|---|---|
| Per-league raw JSON | `data/raw/understat/<League>_<Year>_players.json` | Upstream JSON verbatim |
| Player xG (current) | `data/derived/understat_player_xg.parquet` | Aggregated across the configured seasons |
| Player xG (raw) | `data/derived/understat_player_xg_raw.parquet` | Pre-aggregation, season-grain |
| 21-22 season copy | `data/derived/understat_2122_players.parquet` | Held for backtest reproducibility |

## Allowed write paths

- `data/raw/understat/`
- `data/derived/understat_*.parquet`
- `data/derived/squad_xg_ratings.parquet` (joint output with StatsBomb via `build_squad_xg_ratings.py`)
- `data/derived/team_attack_ratings.parquet` (downstream aggregation)
- `tools/pull_understat_players.py`
- `tools/build_squad_xg_ratings.py`

## Cadence

`weekly` during the season; `on-demand` between seasons. The Orchestrator can call this from the weekly cron once `tools/weekly_pull.py` is extended; today it runs ad-hoc.

## Guardrails

- See [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow).
- Player name overrides must live in `data/derived/player_name_overrides.csv` (when created), **not** inside `tools/build_squad_xg_ratings.py`. See the [data-gaps roadmap Layer 1](data-gaps-roadmap.md#layer-1--player-registry) for the open work item.
- Club data freshness: club seasons end in May/June. After 2026-05-30, the "current" season label is ambiguous — document the chosen window in `MODEL.md` of any consumer.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Modeling](05-modeling.md) | `squad_xg_ratings.parquet`, `team_attack_ratings.parquet`, `understat_player_xg.parquet` (when wired in) | on snapshot |
| [Coverage Audit](quality-coverage-audit.md) | `understat_player_xg_raw.parquet` for `match_rate` per nation | weekly |

## Escalation

- Stop and escalate if: Understat changes its embedded JSON structure (the puller will fail on parse — this is intentional, not silently swallowed).
- Stop and escalate if: a league returns < 50% of the prior season's player count (suggests bot blocking or upstream change).
- Stop and escalate if: fuzzy-match coverage drops below 70% of squad players for any World Cup qualified team — log the unmatched players and surface them to the [Player Registry gap](data-gaps-roadmap.md#layer-1--player-registry).

## Verification

- All league × season JSON files in `data/raw/understat/` exist for the configured window.
- `tools/pull_understat_players.py` exits 0.
- `tools/build_squad_xg_ratings.py` exits 0 and produces a parquet with one row per (nation, player) pair.
- Spot-check: top scorer for the most recent EPL season has xG/90 in a plausible range (~0.4-0.7).
