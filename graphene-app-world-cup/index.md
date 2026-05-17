---
title: WC2026 Analytics — Overview
layout: notebook
---

# WC2026 Analytics

A first look at the curated DuckDB layer through Graphene. Underlying tables live in `data/wc2026.duckdb` (built by `python3 tools/build_duckdb.py`); semantic models in `tables.gsql`.

📖 **[WC2026 — The Story the Model Tells](./wc2026_tournament_report.md)** — narrative tournament report rendered from the latest wc2026-predictor snapshot. Top-2-per-group grid, marquee xG, knockout reach.

## Headline numbers

```sql universe_summary
from curated.dim_player select player_count, count(distinct country_code) as countries
where is_active
```

<BigValue data="universe_summary" value="player_count" title="WC2026 candidates" />
<BigValue data="universe_summary" value="countries" title="Countries represented" />

## Top scorers across all matched sources

The cross-source magic — players with both StatsBomb international and Understat club xG joined on stable `player_id`.

```sql top_scorers
from curated.fact_player_xg
select
  dim_player.display_name as player,
  dim_player.country_code as country,
  total_xg,
  total_minutes,
  total_goals
order by total_xg desc
limit 15
```

<BarChart
  data="top_scorers"
  x="player"
  y="total_xg"
  title="Top 15 by combined xG"
  sort="total_xg desc"
  height="420px"
/>

<Table
  data="top_scorers"
  title="Top 15 — full row detail"
/>

## Per-country squad size

```sql players_per_country
from curated.dim_player
select country_code, player_count
where is_active
order by player_count desc
limit 20
```

<BarChart
  data="players_per_country"
  x="country_code"
  y="player_count"
  title="Players in dim_player by country"
  sort="player_count desc"
  height="320px"
/>

## Team strength matrix

```sql team_ratings_wide
from curated.fact_team_rating
select
  dim_team.team_code as team,
  dim_team.team_name as name,
  rating_type,
  avg_rating
where dim_team.is_wc2026_qualifier
group by 1, 2, 3
```

<Table
  data="team_ratings_wide"
  title="WC2026 qualifiers — rating per rating_type"
  sortable="true"
/>
