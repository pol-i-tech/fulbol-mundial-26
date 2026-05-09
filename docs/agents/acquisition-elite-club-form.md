# Acquisition: Elite-Club Form (UCL / UEL)

## Mission

Pull recent UEFA Champions League and Europa League match minutes for likely WC2026 squad players. This is a *recency* signal: a player who started a UCL semi-final in May 2026 brings different fitness/role evidence than a player who hasn't started for their club in two months. Not a complete player universe — a high-signal layer for the elite-club-exposed subset of the squad pool.

This role is the P1 owner of the [Layer 4 UCL/UEL gap](data-gaps-roadmap.md#layer-4--club-recent-form). **There is no working pull today.** Spec'd in detail by [`player-data-gap-plan.md`](../plans/2026-05-06-player-data-gap-plan.md#immediate-club-level-track-recent-ucl-matches).

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| UEFA match centre / tactical lineups | `https://www.uefa.com/...` | Primary; includes minutes and substitutions |
| Sky Sports teams pages | `https://www.skysports.com/...` | Secondary; lineups, subs, goals, cards |
| Club official match reports | Per-club URLs | When they include lineups/minutes |
| RotoWire / similar | As fallback | Confirmed starters / injury flags only |

Source order from [`player-data-gap-plan.md`](../plans/2026-05-06-player-data-gap-plan.md#source-order) is binding.

## Outputs

| Output | Path | Schema |
|---|---|---|
| Raw HTML/JSON cache | `data/raw/ucl/<YYYY-MM-DD>/` | Upstream verbatim |
| Player-match grain | `data/derived/ucl_recent_player_minutes.csv` | Per `player-data-gap-plan.md` "Data to capture" table |
| Match-squad grain | `data/derived/ucl_recent_match_squads.csv` | Preserves bench players who didn't appear |
| Club form aggregates | `data/derived/club_recent_player_minutes.parquet` | Derived: `ucl_minutes_last_30d`, `ucl_starts_last_30d`, etc. |

## Allowed write paths

- `data/raw/ucl/`
- `data/derived/ucl_recent_*.csv`
- `data/derived/club_recent_player_minutes.parquet`
- `tools/pull_ucl_recent_player_minutes.py` (TODO — does not exist yet)

## Cadence

- `weekly` during the UCL/UEL knockout phase (Feb-May)
- `on-demand` during group stage
- `paused` June-August (off-season)

## Guardrails

- See [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow).
- `source_confidence` field (`official` / `verified_media` / `derived`) required.
- Use as a **confidence/availability signal**, not as a direct team boost — see [`player-data-gap-plan.md`](../plans/2026-05-06-player-data-gap-plan.md#later-join-to-world-cup-candidates).
- Wiring this signal into a model triggers the [refinement-loop protocol](refinement-loop.md).

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Compound-model](modeling-compound-model.md) | `club_recent_player_minutes.parquet` once wired | weekly during knockout phase |
| [Coverage Audit](quality-coverage-audit.md) | `ucl_recent_player_minutes.csv` for elite-club exposure flag | weekly |

## Escalation

- Stop and escalate if: UEFA changes match-centre structure (puller fails — intentional).
- Stop and escalate if: a knockout-round match is missing from the output > 48h after kickoff.
- Stop and escalate if: any consumer treats this layer as a *team-quality* signal rather than a *player availability/form* signal.

## Verification

- `tools/pull_ucl_recent_player_minutes.py` exits 0 (when implemented).
- Output CSV has one row per (player, match) for every UCL/UEL knockout fixture in the configured window.
- Spot-check: for the most recent UCL semi-final, the output captures both starting XIs (22 rows) plus subs (typically 6-10 more rows).

## Status

**Spec'd, not implemented.** [`player-data-gap-plan.md`](../plans/2026-05-06-player-data-gap-plan.md) lists 2 specific target matches (Arsenal-Atletico, Bayern-PSG) for the immediate first run. Picking up this role starts there.
