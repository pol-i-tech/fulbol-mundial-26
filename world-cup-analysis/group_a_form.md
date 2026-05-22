---
title: Group A — How Each Team Is Arriving To WC2026
layout: notebook
---

# How Group A is arriving at WC2026

Group A: **Czech Republic, Mexico, South Africa, South Korea**. Each team plays the other three across the group stage. The question here is *who shows up in form* — at what minutes, and from which leagues — based on what we can see in the curated layer.

```sql group_a_teams
from graphene_cli.curated.dim_team
where team_code in ('CZE', 'MEX', 'RSA', 'KOR')
select team_code, team_name, confederation
order by team_name
```

<Table data="group_a_teams">
  <Column id="team_code" title="FIFA" align="center" />
  <Column id="team_name" title="Country" />
  <Column id="confederation" title="Confederation" align="center" />
</Table>

## 1. Coverage check — what we actually have for each team

Our `fact_player_xg` layer carries two kinds of rows:

- **Understat `club_2526`** — current-season club form (2025-26), the recency signal. Europe-heavy by construction.
- **StatsBomb career-aggregated** — historical international output across covered tournaments.

```sql coverage_by_team
from graphene_cli.curated.fact_player_xg
where dim_player.country_code in ('CZE', 'MEX', 'RSA', 'KOR')
select
  dim_player.nation.team_name as country,
  source,
  period_id,
  count(distinct player_id) as players
group by 1, 2, 3
order by 1, 2, 3
```

<Table data="coverage_by_team" rowShading="true">
  <Column id="country" title="Country" />
  <Column id="source" title="Source" />
  <Column id="period_id" title="Period" />
  <Column id="players" title="Players" align="right" />
</Table>

```sql club_form_counts
from graphene_cli.curated.fact_player_xg
where source = 'understat'
  and period_id = 'club_2526'
  and dim_player.country_code in ('CZE', 'MEX', 'RSA', 'KOR')
select
  dim_player.nation.team_name as country,
  dim_player.nation.confederation as confederation,
  count(distinct player_id) as players_in_top_eu_leagues,
  sum(minutes) as total_minutes,
  round(avg(minutes), 0) as avg_minutes_per_player,
  round(sum(goals), 0) as goals,
  round(sum(xg_total), 1) as xg,
  round(sum(xa_total), 1) as xa
group by 1, 2
order by total_minutes desc
```

<BarChart
  title="Group A — current-season (2025-26) European-club minutes by nation"
  data="club_form_counts"
  x="country"
  y="total_minutes"
  splitBy="confederation"
  sort="total_minutes desc"
  label="true"
  height="320px"
/>

**The headline coverage finding:** of the four Group A nations, **<Value data=club_form_counts column=players_in_top_eu_leagues row=0 />** Mexican and **<Value data=club_form_counts column=players_in_top_eu_leagues row=1 />** Czech players have Understat-tracked club minutes for 2025-26. South Korea contributes a thin cohort, and **South Africa has zero coverage** in our current fact layer — the Bafana Bafana squad plays predominantly in the South African PSL and lower-tier European leagues outside Understat's footprint. Any "who's in form" read for RSA will need a different data source.

## 2. Czech Republic — pulse check

```sql cze_players
from graphene_cli.curated.fact_player_xg
where source = 'understat'
  and period_id = 'club_2526'
  and dim_player.country_code = 'CZE'
select
  dim_player.display_name as name,
  dim_player.current_club as club,
  dim_player.current_league as league,
  dim_player.position as position,
  minutes,
  goals,
  round(xg_total, 2) as xg,
  round(xa_total, 2) as xa,
  round((xg_total + xa_total) / (minutes / 90.0), 3) as xg_xa_per_90
order by minutes desc
```

<Table data="cze_players" rowNumbers="true" compact="true">
  <Column id="name" title="Player" />
  <Column id="club" title="Club" />
  <Column id="league" title="League" />
  <Column id="position" title="Pos" align="center" />
  <Column id="minutes" title="Min" align="right" />
  <Column id="goals" title="G" align="right" />
  <Column id="xg" title="xG" align="right" />
  <Column id="xa" title="xA" align="right" />
  <Column id="xg_xa_per_90" title="xG+xA / 90" align="right" />
</Table>

<BarChart
  title="Czech Republic — xG + xA per 90 (2025-26 club, Understat)"
  data="cze_players"
  x="name"
  y="xg_xa_per_90"
  sort="xg_xa_per_90 desc"
  label="true"
  height="280px"
/>

## 3. Mexico — pulse check

```sql mex_players
from graphene_cli.curated.fact_player_xg
where source = 'understat'
  and period_id = 'club_2526'
  and dim_player.country_code = 'MEX'
select
  dim_player.display_name as name,
  dim_player.current_club as club,
  dim_player.current_league as league,
  dim_player.position as position,
  minutes,
  goals,
  round(xg_total, 2) as xg,
  round(xa_total, 2) as xa,
  round((xg_total + xa_total) / (minutes / 90.0), 3) as xg_xa_per_90
order by minutes desc
```

<Table data="mex_players" rowNumbers="true" compact="true">
  <Column id="name" title="Player" />
  <Column id="club" title="Club" />
  <Column id="league" title="League" />
  <Column id="position" title="Pos" align="center" />
  <Column id="minutes" title="Min" align="right" />
  <Column id="goals" title="G" align="right" />
  <Column id="xg" title="xG" align="right" />
  <Column id="xa" title="xA" align="right" />
  <Column id="xg_xa_per_90" title="xG+xA / 90" align="right" />
</Table>

<BarChart
  title="Mexico — xG + xA per 90 (2025-26 club, Understat)"
  data="mex_players"
  x="name"
  y="xg_xa_per_90"
  sort="xg_xa_per_90 desc"
  label="true"
  height="280px"
/>

> Caveat: this only captures Mexicans playing in Understat-tracked leagues. Liga MX-based starters (the majority of any "El Tri" call-up list) are not represented here. For full coverage, the StatsBomb career-aggregated rows below provide international-tournament context.

## 4. South Korea — pulse check

```sql kor_players
from graphene_cli.curated.fact_player_xg
where source = 'understat'
  and period_id = 'club_2526'
  and dim_player.country_code = 'KOR'
select
  dim_player.display_name as name,
  dim_player.current_club as club,
  dim_player.current_league as league,
  dim_player.position as position,
  minutes,
  goals,
  round(xg_total, 2) as xg,
  round(xa_total, 2) as xa,
  round((xg_total + xa_total) / (minutes / 90.0), 3) as xg_xa_per_90
order by minutes desc
```

<Table data="kor_players" rowNumbers="true" compact="true">
  <Column id="name" title="Player" />
  <Column id="club" title="Club" />
  <Column id="league" title="League" />
  <Column id="position" title="Pos" align="center" />
  <Column id="minutes" title="Min" align="right" />
  <Column id="goals" title="G" align="right" />
  <Column id="xg" title="xG" align="right" />
  <Column id="xa" title="xA" align="right" />
  <Column id="xg_xa_per_90" title="xG+xA / 90" align="right" />
</Table>

> Caveat: South Korea's K League 1 starters (the squad backbone) are outside Understat's coverage. The 2 names above are only the Europe-based players. Son Heung-min has reportedly moved to MLS for 2025-26, which would also push him outside this dataset.

## 5. South Africa — no fact-layer coverage

`fact_player_xg` contains **zero rows** for South African players in any source / period — Understat or StatsBomb. Bafana Bafana's squad is built around the Premier Soccer League (Mamelodi Sundowns, Orlando Pirates, Kaizer Chiefs) plus a handful of Belgian / Portuguese / Saudi-based players. None of those leagues are in our Understat pull, and South Africa has not appeared in any StatsBomb-covered tournament in our dataset.

**To analyze South Africa, the data pipeline needs to add at minimum**: PSL club data (Sofascore would carry this) and CAF qualifier match-level data. Without that, no honest per-player form read is possible. We'd be guessing.

## 6. Cross-team comparison — who arrives with the most club minutes?

```sql all_group_a_ranked
from graphene_cli.curated.fact_player_xg
where source = 'understat'
  and period_id = 'club_2526'
  and dim_player.country_code in ('CZE', 'MEX', 'RSA', 'KOR')
select
  dim_player.nation.team_name as country,
  dim_player.display_name as name,
  dim_player.current_club as club,
  minutes,
  round((xg_total + xa_total) / (minutes / 90.0), 3) as xg_xa_per_90,
  row_number() over (partition by dim_player.country_code order by minutes desc) as rn_minutes
```

```sql top_player_per_nation
from all_group_a_ranked
where rn_minutes = 1
select country, name, club, minutes, xg_xa_per_90
order by minutes desc
```

<Table data="top_player_per_nation">
  <Column id="country" title="Country" />
  <Column id="name" title="Most-used player (2025-26)" />
  <Column id="club" title="Club" />
  <Column id="minutes" title="Min" align="right" />
  <Column id="xg_xa_per_90" title="xG+xA / 90" align="right" />
</Table>

<BarChart
  title="Group A — total European-club minutes per nation (2025-26)"
  data="club_form_counts"
  x="country"
  y="total_minutes"
  sort="total_minutes desc"
  label="true"
  height="280px"
/>

## 7. One-line read per nation

- **Czech Republic** — a balanced cohort of 7 Europe-based players with combined <Value data=club_form_counts column=total_minutes row=1 /> minutes; depth in the German / Italian leagues but no single dominant talisman in xG+xA per 90.
- **Mexico** — the most-used Group A cohort by total Understat-tracked minutes (<Value data=club_form_counts column=total_minutes row=0 />), but only 5 players visible — the analysis is **systematically blind to Liga MX**, which is where most of El Tri actually plays.
- **South Korea** — only 2 Europe-based players in the data, totalling <Value data=club_form_counts column=total_minutes row=2 /> minutes; this is not a full form read for KOR.
- **South Africa** — **no data at all** in `fact_player_xg`. We cannot rank, evaluate, or compare RSA players with the current pipeline.

## Limitations of this view

1. **Understat coverage is the binding constraint.** It captures Europe's top-five leagues plus a handful of others. For Group A, this hurts Mexico, hurts South Korea, and erases South Africa entirely. The Czech Republic suffers least (the bulk of their squad is Europe-based).
2. **No per-player defensive metrics.** Centre-backs and defensive midfielders are evaluated only by minutes and incidental attacking output here.
3. **Squad list is provisional.** `dim_team.is_wc2026_qualifier` confirms the 48 teams in the tournament; the final 26-player squads are not finalised until ~June 2026. Some players visible above may not make the cut; some who will make the cut are missing because their league is not tracked.
4. **No live in-tournament data.** Once WC2026 kicks off (June 11, 2026), a Sofascore / API-Football pull will start producing tournament-grain rows — at which point this page should be refreshed and the data-coverage gap for RSA / KOR / MEX should partially close.
