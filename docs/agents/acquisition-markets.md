# Acquisition: Markets (Kalshi / Polymarket / Pinnacle)

## Mission

Pull current prediction-market and bookmaker prices for every WC2026 market the project covers — match 1X2, outright winner, group winner, team advances, top scorer. These prices are the *only* external benchmark for our model output. Without them, the comparison layer can't compute edge. The role also owns devigging (Power for 1X2, Shin for outrights) and minimum-volume filtering before any "actionable" flag is set downstream.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Kalshi (events + markets) | `https://api.elections.kalshi.com/trade-api/v2` | Unauthenticated reads; series KXMENWORLDCUP, KXWCGAME, KXWCGROUPWIN, KXFIFAADVANCE, KXWCGOALLEADER |
| Polymarket Gamma | `https://gamma-api.polymarket.com` | Unauthenticated reads |
| Pinnacle / Hard Rock | The Odds API | API key required (`ODDS_API_KEY`); $0/mo on free tier |

Rate limits: Kalshi tolerant, Polymarket tolerant. The Odds API free tier is ~500 req/mo — easily handled by weekly polls.

## Outputs

| Output | Path | Schema |
|---|---|---|
| Kalshi raw | `data/raw/kalshi/<YYYY-MM-DD>/<series>_events.json`, `<series>_markets.json` | Upstream verbatim |
| Polymarket raw | `data/raw/polymarket/<YYYY-MM-DD>/<...>.json` | Upstream verbatim |
| Odds API raw | `data/raw/oddsapi/<YYYY-MM-DD>/<sport>.json` | Upstream verbatim |
| Kalshi normalized | `data/derived/kalshi_snapshot_<YYYY-MM-DD>.csv` | Implied probabilities, FIFA3 codes |
| Polymarket normalized | `data/derived/polymarket_snapshot_<YYYY-MM-DD>.csv` | Implied probabilities, FIFA3 codes |
| Pinnacle normalized | `data/derived/pinnacle_snapshot_<YYYY-MM-DD>.csv` | Implied probabilities, FIFA3 codes |

## Allowed write paths

- `data/raw/kalshi/`, `data/raw/polymarket/`, `data/raw/oddsapi/`
- `data/derived/kalshi_snapshot_*.csv`, `polymarket_snapshot_*.csv`, `pinnacle_snapshot_*.csv`
- `tools/weekly_pull.py` (the Kalshi + Polymarket sections)
- `tools/pull_oddsapi.py` (TODO — Pinnacle pull not yet implemented)

## Cadence

`weekly` — Sunday cron via the Orchestrator. Manual `on-demand` for catch-up.

## Guardrails

- Raw quoted prices are informational only. **Do not label a row actionable until devigging and liquidity filters have run** — see [DEVELOPMENT.md — Market normalization](../../DEVELOPMENT.md#market-normalization).
- Devig: Power for 1X2 markets, Shin for outrights/group winners. Documented but [not yet wired into production](data-gaps-roadmap.md#markets) — owned jointly with [Comparison/Edge](synthesis-comparison-edge.md).
- Kalshi outright/group markets include phantom teams at 1-8% — inner-join against known fixtures before devigging. Already implemented in `normalize_kalshi()`; do not regress.
- KXWCGAME ticker regex: `KXWCGAME-26([A-Z]{3})(\d{2})([A-Z]{3})([A-Z]{3})`. Already in `normalize_kalshi()`.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Comparison/Edge](synthesis-comparison-edge.md) | All three `*_snapshot_<date>.csv` files | weekly |
| [Documentation/Learnings](synthesis-documentation-learnings.md) | Snapshot drift across weeks (sharp moves) | continuous |

## Escalation

- Stop and escalate if: Kalshi or Polymarket API returns 5xx for > 1h during the Sunday window — retry once on Monday before failing the weekly pull.
- Stop and escalate if: a market series is missing from a Sunday snapshot but was present the prior Sunday (suggests upstream change, not just zero volume).
- Stop and escalate if: Pinnacle prices via The Odds API exceed free-tier monthly quota — this means we're polling too often.
- Stop and escalate if: any consumer flags an "actionable" edge before devigging is implemented in the comparison layer.

## Verification

- All three snapshot CSVs exist for the dated weekly run.
- Kalshi snapshot includes rows for every active series (KXMENWORLDCUP, KXWCGAME, KXWCGROUPWIN, KXFIFAADVANCE, KXWCGOALLEADER) where markets exist.
- Implied probabilities are in [0, 1] and pass the validator's sum check (≥ 0.99 and ≤ 1.01 per market) *post-devig* once devigging lands.
- `tools/weekly_pull.py` produces `results/comparisons/<date>/comparison.csv` with non-null prices joined.
