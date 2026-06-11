# WC2026 simulation — data lineage

What actually drives the prediction engine vs. what is narrative color only.

## Engine inputs (football signals — these decide the predictions)

| Engine input | Curated table | Upstream source | Notes |
|---|---|---|---|
| `fifa_points` | `curated.dim_team_current` | FIFA world ranking snapshot (`fact_team_fifa_ranking`) | Elo component |
| `attack` (xG/90 proxy) | `curated.fact_team_rating` (`rating_type='attack'`) | `raw.team_attack_ratings` ← `data/derived/team_attack_ratings.parquet` ← `tools/build_squad_xg_ratings.py` | **Player-xG derived** |
| `defense` (xGA/90 proxy) | `curated.fact_team_rating` (`rating_type='defense'`) | `raw.team_defensive_ratings` ← squad/defensive aggregation | **Player-xG derived** |
| `recent_form` | `curated.fact_team_rating` (`rating_type='recent_form'`) | `raw.team_ratings_all_models` (`M3_RecentForm`) | Form component |

**Player-data provenance for attack/defense:** `tools/build_squad_xg_ratings.py` builds team attack ratings by aggregating individual player xG — StatsBomb national-team xG/90 (WC22 / Euro24 / Copa24) blended `0.4` with Understat 2024-25 club xG/90 `0.6`, with Bayesian shrinkage toward a conservative prior for players below ~180 reliable minutes. So **team data and player data both feed the engine**: the team rating *is* the squad's aggregated player xG.

## Narrative color only (NOT in the engine)

| Color input | Curated table | Used for |
|---|---|---|
| GDP per capita, population | `curated.dim_team_current` (`gdp_per_capita_usd_latest`, `population_latest`), `curated.fact_team_economics` | "David vs Goliath" / giant-killer lines in `REPORT.md` |
| Top players by xG/90 | `curated.fact_player_xg_per_90` + `curated.dim_player` | "the men who carry each contender" lines |

Economics is read **after** the simulation, purely for prose. It never enters `ensemble_probs`, so it cannot bias the model against teams that overperform their GDP (Argentina, Morocco, Senegal, etc.).

## Reproducibility

Engine config: `ensemble = 0.35·Elo + 0.45·Poisson(xG) + 0.20·Form` (validated in the WC2022 backtest). Same `--seed` → identical `probabilities.csv` and `per_game.csv`.
