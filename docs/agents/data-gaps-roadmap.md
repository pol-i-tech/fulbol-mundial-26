# Data Gaps Roadmap

This document is the routing layer between the project's known data gaps and the Acquisition roles in [the catalog](README.md). It is **not** a re-derivation of the existing acquisition strategy — it points at it.

Source documents (read these first):

- [`docs/plans/2026-05-06-world-cup-player-data-acquisition-strategy.md`](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md) — full four-layer data architecture and coverage targets
- [`docs/plans/2026-05-06-player-data-gap-plan.md`](../plans/2026-05-06-player-data-gap-plan.md) — current player-data limitations and required guardrails
- [`DEVELOPMENT.md` priority stack](../../DEVELOPMENT.md#current-priority-stack) — the canonical priority frame; this roadmap inherits from it

## Priority frame

The repo's priority stack governs all data work:

1. Guardrails and validation
2. **Player-data coverage** ← most gaps below sit here
3. Market normalization
4. Model consolidation
5. Then advanced features (sim, dashboards, new markets)

Each gap below is bucketed against this stack:

- **P0** — blocks production betting output until closed
- **P1** — known degradation; address before next major model refresh
- **P2** — known but acceptable today; revisit after P0/P1 are clear

The stop-condition that promotes a P1 to P0 is named per gap.

## Gaps by data layer

### Layer 1 — Player Registry

| Gap | Owning role | Priority | Stop-condition (promotes to P0) |
|---|---|---|---|
| No canonical `data/derived/player_registry.parquet` exists. Joins today happen on display name + fuzzy match. | [Coverage Audit](quality-coverage-audit.md) seeds the registry; per-source acquisition roles populate IDs | P1 | Two distinct players collide under the same fuzzy match in a snapshot that influences a comparison |
| No central `data/derived/player_name_overrides.csv`. Manual mappings live inside `tools/build_squad_xg_ratings.py`. | [Understat](acquisition-understat.md) and [StatsBomb](acquisition-statsbomb.md) extract overrides on next pass | P1 | Any new contributor adds a hardcoded override to a `tools/` script |

Targets per [acquisition strategy](../plans/2026-05-06-world-cup-player-data-acquisition-strategy.md#layer-1-player-registry).

### Layer 2 — Candidate Pool

| Gap | Owning role | Priority | Stop-condition |
|---|---|---|---|
| `data/derived/wc2026_player_candidates.parquet` does not exist. Today `squad_xg_ratings.parquet` is treated as a likely-squad proxy. | [WC2026 Squads](acquisition-wc2026-squads.md) | P1 | FIFA publishes preliminary 35-55 player lists and we ignore them |
| No `squad_status` field separating `historical_pool` / `recent_callup` / `preliminary` / `confirmed` / `excluded`. | [WC2026 Squads](acquisition-wc2026-squads.md) | P1 | A model treats a 2022-era player as confirmed for 2026 |

### Layer 3 — National Recent Usage

| Gap | Owning role | Priority | Stop-condition |
|---|---|---|---|
| No structured pull of FIFA / confederation / federation match reports for recent qualifiers and friendlies. martj42 covers results but not lineups, minutes, or substitutions. | [National Lineups](acquisition-national-lineups.md) | **P0** for any model that wants to use lineup-level signal | Any modeling role wires lineup data into a snapshot before this exists |
| Nations League and WC qualifying xG not pulled. [Documented as the highest-impact missing signal](../solutions/best-practices/model-roles-and-best-use-2026-04-28.md) — closes the 6-pt accuracy gap on xG-Poisson. | [StatsBomb](acquisition-statsbomb.md) (if open data covers) or [National Lineups](acquisition-national-lineups.md) (verified-media fallback) | **P0** for xG-Poisson refinement | Next refinement-loop pass on xG-Poisson without this layer |

### Layer 4 — Club Recent Form

| Gap | Owning role | Priority | Stop-condition |
|---|---|---|---|
| UCL / UEL recent player minutes not pulled. Spec'd in detail in [`player-data-gap-plan.md` "Immediate Club-Level Track"](../plans/2026-05-06-player-data-gap-plan.md#immediate-club-level-track-recent-ucl-matches). | [Elite-Club Form](acquisition-elite-club-form.md) | P1 | Major UCL/UEL knockout round happens and we have no minutes data for the 50+ likely-squad players who started |
| Club data freshness not tracked. Stale club data silently treated as current. | [Understat](acquisition-understat.md) | P1 | Any model commits without `club_data_freshness_days` available |
| Coverage uneven by region — top European leagues well covered, CONMEBOL / CONCACAF / AFC players thin. | Cross-cutting; primary owner is [Coverage Audit](quality-coverage-audit.md) for surfacing, then per-source roles to close | P1 | Coverage report shows < 50% match rate for any World Cup qualified team |

### Markets

| Gap | Owning role | Priority | Stop-condition |
|---|---|---|---|
| Devigging not implemented in production. Power devig for 1X2, Shin for outrights — both documented in `DEVELOPMENT.md` but not wired into the comparison output today. | [Markets](acquisition-markets.md) + [Comparison/Edge](synthesis-comparison-edge.md) | **P0** for actionable bet output | Any "actionable" bet flagged before devigging passes |
| Pinnacle / Hard Rock prices via The Odds API not pulled. Edge rule requires `model_p > Pinnacle_p + 1.5%`. | [Markets](acquisition-markets.md) | **P0** for edge calculation | Edge flagged without Pinnacle comparison |
| Kalshi outright/group markets have phantom teams at 1-8% (operator-priced). Already documented in `DEVELOPMENT.md`. Filter exists in `normalize_kalshi()` but volume threshold not enforced in comparison. | [Markets](acquisition-markets.md) | P1 | Comparison output flags edge on a market with `min_volume = 0` |

### WC2026 squad confirmation

| Gap | Owning role | Priority | Stop-condition |
|---|---|---|---|
| Final 26-player squad confirmation pipeline not built. FIFA squad release is 2026-05-25 (with confederation-final exception through 2026-05-30). | [WC2026 Squads](acquisition-wc2026-squads.md) | **P0 from 2026-05-25** | FIFA publishes final squads and we are still using preliminary or historical pools |

## Cross-cutting items

- **Injury / suspension feeds** — listed as future work in `DEVELOPMENT.md`. No source selected yet. Scope this as research before assigning a role.
- **Paid API evaluation** (API-FOOTBALL or SportMonks) — `acquisition-strategy.md` Layer 4 calls for a scoped evaluation of one paid API before adopting. This is an evaluation, not an ongoing acquisition. Scope it as a one-off task and document findings under `docs/solutions/best-practices/`.

## How this document gets updated

- The [Coverage Audit](quality-coverage-audit.md) role refreshes the gap status weekly via `tools/audit_player_coverage.py` and any other observable signals.
- When a gap closes, mark it `RESOLVED — see <PR or commit>` and leave the row for one cycle so it stays in diff history. Then remove on the next refresh.
- New gaps appear here only after the [Documentation / Learnings](synthesis-documentation-learnings.md) role files them as a learning under `docs/solutions/`. No silent gap addition.
