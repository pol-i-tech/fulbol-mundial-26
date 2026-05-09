# Acquisition: National Lineups

## Mission

Pull starting XIs, substitutes, substitutions, and minutes-played for recent international fixtures (qualifiers, Nations League, friendlies) directly from FIFA Match Centre, confederation match reports, and federation match reports. This layer tells us who national teams *actually use* — the gap between callup lists and on-pitch minutes. **There is no working pull for this today.** martj42 covers results but not lineups.

This role is documented as a P0 owner of the [Layer 3 gap](data-gaps-roadmap.md#layer-3--national-recent-usage). The role spec is live; the script is TODO.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| FIFA Match Centre | `https://www.fifa.com/fifaplus/en/match-centre` (and per-match URLs) | Best source when available; structure varies by competition |
| UEFA match reports | `https://www.uefa.com/...` | Lineups + tactical lineups for European qualifiers, Nations League |
| Confederation match reports | CONMEBOL, CONCACAF, AFC, CAF, OFC | Per-confederation; varying coverage |
| Federation match reports | National federation pages | Backup |
| Verified media (Sky Sports, etc.) | Used only when official data is missing | See [acquisition strategy source order](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#layer-3-national-team-recent-usage) |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Raw HTML/JSON cache | `data/raw/national_lineups/<source>/<YYYY-MM-DD>/` | Upstream verbatim |
| Player-match minutes | `data/derived/national_recent_player_minutes.parquet` | Per [acquisition strategy Layer 3](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#layer-3-national-team-recent-usage) |
| Match-squad grain | `data/derived/national_recent_match_squads.parquet` | Preserves bench players who didn't appear |

## Allowed write paths

- `data/raw/national_lineups/`
- `data/derived/national_recent_*.parquet`
- `tools/pull_national_lineups.py` (TODO — does not exist yet)

## Cadence

- `weekly` during international windows (March, June, September, October, November)
- `on-demand` outside windows for late-released match reports

## Guardrails

- See [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow).
- Source priority order from [acquisition strategy Layer 3](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#layer-3-national-team-recent-usage) is binding — do not pull from verified media when official data exists.
- `source_confidence` field (`official` / `verified_media` / `derived`) is required on every row.
- **No automated scraping of bot-protected sites.** If a confederation page blocks the puller, fall back to verified media with the `verified_media` label, do not bypass.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Compound-model](modeling-compound-model.md) | `national_recent_player_minutes.parquet` once wired in | weekly |
| [Coverage Audit](quality-coverage-audit.md) | `national_recent_*.parquet` for per-nation national-minutes columns | weekly |

## Escalation

- Stop and escalate if: a target source's HTML structure changes mid-window (the puller will fail; do not silently produce stale data).
- Stop and escalate if: official data is missing for a competitive match > 7 days after the match (escalate to ask whether to fall back to verified media).
- Stop and escalate if: any backtest using this data fails the [refinement-loop](refinement-loop.md) calibration check.

## Verification

- `tools/pull_national_lineups.py` exits 0 (when implemented).
- Output parquet has one row per (player, match) for every fixture in the configured window.
- Every row has a non-null `source_url` and `source_confidence`.
- For each fixture in the latest international window, `data/derived/national_recent_player_minutes.parquet` has between 11 and 30 player rows (starters + subs).

## Status

**Spec'd, not implemented.** Picking up this role means writing `tools/pull_national_lineups.py` from scratch. The acquisition strategy's source order and field list (linked above) is the design doc; this spec is the contract.
