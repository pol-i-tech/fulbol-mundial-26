# UCL Event Data Pipeline — Ideation
**Date:** 2026-04-29
**Focus:** Game-by-game Champions League event data scraper for WC2026 prediction model enrichment
**Status:** Survivors ranked, ready for brainstorm

---

## Grounding Summary

- **Project:** Python WC2026 prediction workbench. Tools follow: fetch → raw JSON in `data/raw/<source>/<YYYY-MM-DD>/` → derived parquets in `data/derived/`
- **Already built:** StatsBomb open data (115 matches), Understat player xG, martj42 form CSV (49K+ results), Kalshi/Polymarket market snapshots, `squad_xg_ratings.parquet` (untracked, not yet wired in)
- **Highest-leverage gap:** xG-Poisson accuracy is 40.6% vs. Form at 46.9% — root cause is sparse training data (115 matches). UCL has ~125 games/season.
- **Key blocker:** Match ID discovery — UCL match IDs on scoresway.com are opaque 25-char strings. Discovery approach unknown.
- **Data source visible:** `api.performfeeds.com` (Stats Perform / Opta) with endpoints: `match/{id}`, `matchstats/{id}`, `squads/{id}`
- **Existing untracked data:** `data/raw/statsbomb/euro2024/`, `data/raw/statsbomb/wc2022/` — partially pulled, not processed
- **FBref:** Hard-blocked by Cloudflare. Do not attempt.

---

## Survivors (Ranked)

### #1 — Wire `squad_xg_ratings.parquet` into Compound Model Now
**Impact: Immediate / Zero new data collection required**

The parquet already exists (`data/derived/squad_xg_ratings.parquet`, untracked). `build_squad_xg_ratings.py` builds it. The compound model hasn't consumed it yet. This is the highest-ROI action in the entire pipeline — ship this before writing a single line of scraper code.

**Why it survives:** Zero new infrastructure. The data is sitting there. Every hour spent building a scraper before wiring in existing data is waste.

**Grounding:** `compound-model/MODEL.md` (modified), `data/derived/squad_xg_ratings.parquet` (untracked)

**Next step:** → ce:brainstorm "wire squad_xg_ratings into compound model"

---

### #2 — Expand StatsBomb Training Data (EURO2024 + La Liga Already Partially Pulled)
**Impact: High / No new scraping infrastructure**

`data/raw/statsbomb/euro2024/` and `data/raw/statsbomb/wc2022/` exist as untracked directories — data is already partially pulled. The existing `pull_statsbomb.py` uses a `TARGETS` list of competition IDs. Adding EURO 2024, La Liga, PL, Bundesliga (all in StatsBomb free data) could expand the training corpus from 115 to 400+ matches without any new data source. StatsBomb open data covers domestic leagues for WC2026-squad players.

**Why it survives:** Same pattern, same code, higher leverage. More xG training data is the stated root cause of the accuracy gap.

**Grounding:** `tools/pull_statsbomb.py` TARGETS list, `data/raw/statsbomb/euro2024/`

**Next step:** → Run `pull_statsbomb.py` with EURO2024 + La Liga competition IDs, process into parquet

---

### #3 — Sofascore as Primary UCL Scrape Target (Not Scoresway)
**Impact: High / Eliminates match-ID discovery problem**

`api.sofascore.com/api/v1/event/{id}/incidents` is a well-documented public API. Match IDs are **sequential integers** discoverable via `api.sofascore.com/api/v1/sport/football/scheduled-events/{date}`. Returns: shot maps, xG, lineups, substitutions, cards — the full event stream. No authentication required. Strong community tooling exists. This replaces the entire Scoresway/Opta reverse-engineering effort.

**Why it survives:** The match-ID discovery problem (opaque 25-char strings on Scoresway) is the hardest part of the Scoresway approach. Sofascore uses sequential IDs discoverable by date. Same data, less friction.

**Adversarial:** Sofascore ToS prohibits scraping; could block. Mitigation: low request rate, user-agent rotation, respect robots.txt.

**Grounding:** Match IDs described as opaque discovery problem in context; Sofascore well-documented as public-facing sports data source

**Next step:** → ce:brainstorm "UCL scraper via Sofascore API"

---

### #4 — Understat Already Has UCL xG (Lowest-Friction Path)
**Impact: High / Existing pull pattern, zero new infrastructure**

Understat tracks Champions League with shot-level xG, player positions, and game state. It uses the same JSON-in-HTML pattern as domestic leagues, already scraped via `soccerdata` in `tools/pull_understat_players.py`. The existing pattern extends directly: add `UCL` to the league list. No match ID discovery, no auth, no browser automation.

**Why it survives:** The existing Understat scraper (`soccerdata` library) already handles the session/cookie/ID complexity. This is potentially a 1-line addition to the existing script.

**Adversarial:** Understat may not have complete UCL coverage (some clubs missing); verify coverage before relying on it. Also `soccerdata` for Understat may have rate-limit quirks.

**Grounding:** `tools/pull_understat_players.py`, `data/derived/statsbomb_player_xg.parquet` (target schema)

**Next step:** → Verify Understat UCL coverage, then extend `pull_understat_players.py`

---

### #5 — Unified Player Name / ID Resolution Layer
**Impact: High / Unlocks all cross-source joins**

Every data source uses different player name formats: Opta IDs, StatsBomb UUIDs, Understat string names, Wikipedia canonical names, WC2026 squad names from `data/raw/squads/`. Without a canonical resolution table, UCL data will silently fail to join with WC2026 squads for the most important players (accented names, double surnames, short forms). Build `data/derived/player_id_map.parquet` once, route all joins through it.

**Why it survives:** Fuzzy matching post-hoc is acknowledged as a known pain point. This is the architectural fix, not a patch.

**Grounding:** `data/raw/squads/`, `data/derived/statsbomb_player_xg.parquet`, `compound-model/MODEL.md` (formula references player-level xG)

**Next step:** → ce:brainstorm "player name unification layer"

---

### #6 — Three-Endpoint Fan-Out + Pull Manifest (Core Scraper Architecture)
**Impact: Medium-High / The backbone of any UCL scraper**

Whether the source is Sofascore, Understat, or Scoresway: the scraper needs to (a) fetch all three data payloads per match atomically, (b) store raw JSON in `data/raw/<source>/<YYYY-MM-DD>/`, (c) maintain a `pulled_matches.json` manifest to skip already-fetched matches, and (d) apply rate-limiting with jittered backoff. This is the reusable scaffold regardless of which source wins.

**Why it survives:** Every other scraping idea depends on this infrastructure being correct. Getting the atomic-write + idempotency pattern right once pays off for all future sources.

**Grounding:** `tools/weekly_pull.py` (pattern to extend), `data/raw/kalshi/2026-04-28/` (model for raw JSON layout)

**Next step:** → Implement as `tools/pull_ucl_events.py` following weekly_pull.py pattern

---

### #7 — UCL Match Importance Weight + Defender/GK xG-Against Ratings
**Impact: Medium / Closes two model gaps simultaneously**

Two separate but combinable improvements: (a) Derive the UCL match importance weight by regressing WC2022 player xG performance against their prior UCL xG (using the existing backtest in `results/comparisons/wc2022-backtest/`) rather than guessing. (b) Build `squad_defense_ratings.parquet` symmetric to `squad_xg_ratings.parquet` — tracking xGA-per-90 for projected WC starters. The Poisson model is currently attack-only; defense prior makes scoreline distributions asymmetric and more accurate.

**Why it survives:** These compound: calibrated UCL weights + defense ratings together address the known Poisson underfitting from two directions (data quality + model structure).

**Adversarial:** WC2022 backtest sample is small (45 matches); regressing UCL→WC performance has high variance. Treat derived weight as a prior to be adjusted, not a hard number.

**Grounding:** `results/comparisons/wc2022-backtest/`, `compound-model/MODEL.md` (recency weights, attack-only formula)

**Next step:** → ce:brainstorm "defense ratings + UCL importance weight calibration"

---

## Eliminated (with reasons)

| Idea | Reason |
|------|--------|
| Session-cookie harvester | Opta endpoints appear unauthenticated (network tab shows plain GETs); Playwright overhead is premature |
| ETag incremental cache | File-existence check is sufficient; YAGNI |
| FBref mirror scraping | ToS grey area, brittle HTML, not worth the fragility |
| Plugin interface abstraction | Premature unification of 3-4 scripts; adds indirection, removes clarity |
| Synthetic UCL proxy from domestic xG | Empirically unvalidated scaling coefficient adds model risk |
| VAR/disciplinary flags | Small effect size on 90-min WC outcomes; marginal |
| Attendance → home-advantage calibration | WC neutral-site effect better handled by dropping home term than calibrating it |
| Partial-match live-update re-pull | Subsumed: a `status` field in the pull manifest handles this |

---

## Recommended Sequence

1. **Today (no new data):** Wire `squad_xg_ratings.parquet` into compound model. Measure accuracy delta.
2. **This week:** Run `pull_statsbomb.py` with EURO2024 + additional competition IDs. Process into parquet.
3. **Next:** Verify Understat UCL coverage. If complete, extend `pull_understat_players.py`.
4. **If Understat UCL is incomplete:** Build Sofascore scraper using the three-endpoint fan-out scaffold.
5. **Once data flows:** Build player ID unification layer. Calibrate UCL importance weights.
6. **Final model pass:** Add defense ratings as Poisson asymmetry prior.

---

## Open Questions

- Does Understat cover all 32 UCL clubs (especially non-Big-5 clubs)?
- Which StatsBomb competition IDs are available for EURO2024, La Liga, etc.?
- Is `results/ensemble-v2/` a prior attempt at the meta-learner idea?
- What's in `data/derived/team_attack_ratings.parquet` (already untracked)?
