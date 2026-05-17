---
title: WC2026 — The Story the Model Tells
layout: notebook
---

# WC2026 — The Story the Model Tells

<!--
    Source of truth for the data blocks below is the latest wc2026-predictor
    snapshot, currently `results/wc2026-predictor/2026-05-16/`. When a new
    snapshot lands, update the SNAPSHOT_DATE constant in the first SQL block —
    every other block reads from the named CTE.

    Prose sections are wrapped in <!-- agent prose: <id> --> ... <!-- /agent prose: <id> -->.
    Fill them per docs/agents/storytelling-report-writer.md (tone rules,
    forbidden phrases, word budgets).

    Plan: docs/plans/2026-05-16-001-feat-tournament-report-writer-agent-plan.md
-->

<!-- agent prose: opening_hook -->
*~80 words, opening hook. Framing: this is a forecast; the forecast is a guess; here's what the guess looks like. End with a humility framing from the role spec.*
<!-- /agent prose: opening_hook -->

```sql snapshot
-- Wires the wc2026-predictor outputs into named tables the rest of the
-- notebook reads from. Update the date string when a new snapshot lands.
with snapshot as (select '2026-05-16' as snapshot_date)
select snapshot_date from snapshot
```

```sql probabilities
-- Per-team stage-reach probabilities for the current snapshot.
select *
from read_csv_auto(
  '../results/wc2026-predictor/' || (select snapshot_date from snapshot) || '/probabilities.csv'
)
```

```sql marquee_games
-- Up to 8 group-stage fixtures the model flags as marquee (both teams ≥ 50% to advance).
select *
from read_csv_auto(
  '../results/wc2026-predictor/' || (select snapshot_date from snapshot) || '/marquee_games.csv'
)
```

```sql team_metadata
-- Team display names + confederation, joined from the curated dim.
select team_code, team_name, confederation
from curated.dim_team
where is_wc2026_qualifier
```

## The favorites

<!-- agent prose: favorites -->
*~150 words. The top 5 by p_champion, the path each one needs to take, what the model sees in their group. Use "the model gives …" framing at least once.*
<!-- /agent prose: favorites -->

```sql top12_knockout_reach
-- Top 12 teams by p_champion with full stage-reach percentages. Renders as a
-- table; sort descending by p_champion. Each percentage shown to 1 decimal.
select
  p.team                                  as team,
  m.confederation                         as confederation,
  round(p.p_r16 * 100, 1)                 as "R16 %",
  round(p.p_qf * 100, 1)                  as "QF %",
  round(p.p_semi * 100, 1)                as "Semi %",
  round(p.p_final * 100, 1)               as "Final %",
  round(p.p_champion * 100, 1)            as "Champion %"
from probabilities p
left join team_metadata m on m.team_name = p.team
order by p.p_champion desc
limit 12
```

<Table data="top12_knockout_reach" title="Top 12 by Champion %" sortable="true" />

<BarChart
  data="top12_knockout_reach"
  x="team"
  y="Champion %"
  title="Top 12 contenders — model-estimated champion probability"
  sort="Champion % desc"
  height="360px"
/>

## The group stage in one breath

<!-- agent prose: group_stage -->
*~180 words. Group-by-group highlights — the tight groups and the foregone conclusions. Let the grid below carry the data; the prose just adds story. Use a humility framing once.*
<!-- /agent prose: group_stage -->

```sql top2_in_group_grid
-- 12-card top-2 layout. Each row: group letter, team name, p_top2_in_group %.
-- Sorted within group by p_top2_in_group descending. Render as a faceted
-- table (by group_letter) or — if Graphene supports it — as a 12-card grid
-- mirroring the Figure 1 reference image.
with tournament_groups as (
  select 'A' as group_letter, ['South Korea','Czechia','Mexico','South Africa']                as teams union all
  select 'B', ['Switzerland','Qatar','Canada','Bosnia and Herzegovina']                        union all
  select 'C', ['Brazil','Morocco','Scotland','Haiti']                                          union all
  select 'D', ['Australia','Turkey','USA','Paraguay']                                          union all
  select 'E', ['Germany','Ecuador','Ivory Coast','Curaçao']                                    union all
  select 'F', ['Netherlands','Japan','Sweden','Tunisia']                                       union all
  select 'G', ['Belgium','Iran','Egypt','New Zealand']                                         union all
  select 'H', ['Spain','Uruguay','Saudi Arabia','Cape Verde']                                  union all
  select 'I', ['France','Senegal','Norway','Iraq']                                             union all
  select 'J', ['Argentina','Austria','Algeria','Jordan']                                       union all
  select 'K', ['Portugal','Colombia','Uzbekistan','DR Congo']                                  union all
  select 'L', ['England','Croatia','Panama','Ghana']
),
flat as (
  select group_letter, unnest(teams) as team_name
  from tournament_groups
)
select
  flat.group_letter                       as "Group",
  flat.team_name                          as "Team",
  round(p.p_top2_in_group * 100, 0)::int  as "Top-2 %"
from flat
left join probabilities p on p.team = flat.team_name
order by flat.group_letter, p.p_top2_in_group desc
```

<Table data="top2_in_group_grid" title="Likelihood of making it into the top 2 in each group" sortable="false" />

## The games to watch

<!-- agent prose: games_to_watch -->
*~180 words. Call out 3-4 marquee fixtures by name. What the model sees (lambdas, p_top2 split, 1X2). Why the model might be wrong — at least one specific way. Use one of the forbidden-phrase substitutes.*
<!-- /agent prose: games_to_watch -->

```sql marquee_xg_view
-- One row per marquee game with lambdas and 1X2 split. Renders as a chart per
-- row (home/away λ side-by-side bars + p_home/p_draw/p_away stack annotation)
-- or as a clean table with bars inline, depending on what Graphene's chart
-- primitives support.
select
  group_letter                         as "Group",
  kickoff_date                         as "Date",
  home_team || ' vs ' || away_team     as "Match",
  round(lam_home, 2)                   as "λ home",
  round(lam_away, 2)                   as "λ away",
  round(p_home * 100, 1)               as "Home %",
  round(p_draw * 100, 1)               as "Draw %",
  round(p_away * 100, 1)               as "Away %",
  round(p_top2_home * 100, 0)::int     as "Home top-2 %",
  round(p_top2_away * 100, 0)::int     as "Away top-2 %"
from marquee_games
order by (p_top2_home + p_top2_away) desc
```

<Table data="marquee_xg_view" title="Marquee group-stage matchups" sortable="true" />

## The dark horses and the cautionary tales

<!-- agent prose: dark_horses -->
*~150 words. One team the model loves you should doubt; one team the model dismisses you should watch. Use one of the required framings. Editorialize about the model's blind spots, not the data itself.*
<!-- /agent prose: dark_horses -->

## A word from the model

<!-- agent prose: closing -->
*~60 words. Closing humility paragraph naming specific blind spots the model has (no player data, FIFA-rank snapshot frozen in time, no injuries, no tactics, no weather). Required framing once.*
<!-- /agent prose: closing -->

## How the model works

<!-- agent prose: methodology -->
*~100 words. Methodology footnote — variables and data sources at concept level only. NO pull-script paths, NO API endpoint names. Acceptable mentions: "international match results since 2022", "current FIFA World Ranking", "country-level GDP and population", "host-country boost". Link to results/wc2026-predictor/MODEL.md for the full card.*
<!-- /agent prose: methodology -->
