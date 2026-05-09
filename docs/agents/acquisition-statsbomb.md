# Acquisition: StatsBomb xG

## Mission

Pull and aggregate StatsBomb open-data event-level xG for the international tournaments that matter to WC2026 modeling: WC2018, WC2022, Euro2020, Euro2024, Copa2024. This is the only source of *real* (event-attributed) xG for international football the project uses. The xG-Poisson model and the player-level squad ratings depend entirely on it.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| StatsBomb open-data repo | `https://github.com/statsbomb/open-data` | MIT-licensed; cached per-match JSON locally |
| Match list | `tools/pull_statsbomb.py` hard-coded competition IDs | Update this list when StatsBomb releases a new tournament |

Rate limit: StatsBomb open-data is on GitHub; well-cached locally so re-runs are fast.

## Outputs

| Output | Path | Schema |
|---|---|---|
| Per-match cache | `data/raw/statsbomb/matches/<match_id>.json` | Upstream verbatim |
| Player xG aggregate | `data/derived/statsbomb_player_xg.parquet` | Per-player tournament xG totals |
| Team xG aggregate | `data/derived/statsbomb_team_xg.parquet` | Per-match team-level xG |
| Player summary | `data/derived/sb_player_summary.parquet` | Aggregated tournament participation |
| Player stats with pedigree | `data/derived/sb_player_stats_pedigree.parquet` | xG-weighted by tournament tier |

## Allowed write paths

- `data/raw/statsbomb/`
- `data/derived/statsbomb_*.parquet`
- `data/derived/sb_player_*.parquet`
- `tools/pull_statsbomb.py`
- `tools/aggregate_statsbomb_players.py`
- `tools/aggregate_statsbomb_pedigree.py`
- `tools/build_wc2022_player_xg.py`

## Cadence

`on-demand` — only when StatsBomb publishes a new tournament's open data. Not part of the weekly cron.

## Guardrails

- Raw snapshot immutability — see [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow).
- Idempotency — re-running with no upstream change must produce identical derived outputs.
- Tournament inclusion is a [subjective adjustment](../../DEVELOPMENT.md#subjectivity-and-bias-policy): adding a new tournament to the aggregator changes downstream xG-Poisson outputs and triggers the [refinement-loop protocol](refinement-loop.md).

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [xG-Poisson](modeling-poisson-xg.md) | `statsbomb_team_xg.parquet`, `statsbomb_player_xg.parquet` | on update |
| [Compound-model](modeling-compound-model.md) | `sb_player_stats_pedigree.parquet` | on update |
| [Coverage Audit](quality-coverage-audit.md) | `sb_player_summary.parquet` for national-team minutes columns | weekly |

## Escalation

- Stop and escalate if: a new tournament's competition_id schema differs from the cached structure.
- Stop and escalate if: aggregated xG totals drop > 5% for a tournament that was previously stable (suggests StatsBomb re-revised the data).
- Stop and escalate if: a player previously aggregated disappears from the new aggregation pass.

## Verification

- `tools/pull_statsbomb.py` exits 0 with new tournament data cached.
- `tools/aggregate_statsbomb_players.py` produces the four parquet files.
- Spot-check: top-10 xG players for the latest tournament look plausible (Mbappé, Messi, etc.).
- `tools/validate_predictions.py --all` still passes for any model that consumes the new aggregation.
