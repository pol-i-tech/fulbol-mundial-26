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
What every model that has ever predicted a World Cup has in common is this: it was wrong about something. The 2026 forecast that follows is no different. The model gives Germany about a 7.9% chance to lift the trophy and Argentina about a 4.9% chance — small numbers because there are 48 teams and a lot of variance baked into a one-month tournament. Read this as an estimate, not a prophecy.
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
At the top, the field looks unusually flat. The model gives Germany about a 7.9% chance to be champion, France about 7.0%, Belgium about 6.2%, Norway about 6.0%, and Brazil about 5.7%. That's five teams within two percentage points of each other — closer than any pre-tournament read on a recent World Cup has produced. Germany's path runs through Group E (Ecuador, Côte d'Ivoire, Curaçao), which the model calls the easiest top-of-group draw of the favorites. France is in Group I with Norway — the only group containing two top-six contenders, which is also why both of them get punished on champion probability relative to their underlying lambdas. Belgium gets Group G with Iran, Egypt, and New Zealand; the model thinks Belgium walks out of the group at 77% and then has to beat one of the other top-five to make a semifinal.
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
The grid below carries the data, so the prose just flags the shape. Germany (Group E), Belgium (Group G), Portugal (Group K), England (Group L), and Netherlands (Group F) are the cleanest top-of-group bets — each crosses 73% to advance and faces nobody else above 65%. Group I is the death group: France 71% and Norway 67% — two teams above any other group's runner-up percentage in the entire tournament. Brazil pulls Scotland in Group C, where the model gives Scotland about a 50% chance to advance against a 72%-Brazil that would normally bulldoze its way through. The Asian + Concacaf groups (A, D, J) are open. Group A has South Korea 48% / Mexico 45% / South Africa 40% — the closest group in the bracket, where any of three teams could finish second. If the model is right — and history says it routinely isn't — the broad story of the group stage is "favorites mostly survive, Group I is a sword fight, and Group A is a coin toss for second place."
<!-- /agent prose: group_stage -->

```sql top2_in_group_grid
-- 12-card top-2 layout. Each row: group letter, team name, p_top2_in_group %.
-- Sorted within group by p_top2_in_group descending. Render as a faceted
-- table (by group_letter) or — if Graphene supports it — as a 12-card grid
-- mirroring the Figure 1 reference image.
-- Team names are the canonical curated.dim_team display names used in
-- probabilities.csv (not the tournament.json display strings — see the
-- alias map in methodology/wc2026-predictor/simulate.py for the
-- canonical/display divergence: Czechia -> Czech Republic, USA ->
-- United States, etc.).
with tournament_groups as (
  select 'A' as group_letter, ['Korea Republic','Czech Republic','Mexico','South Africa']      as teams union all
  select 'B', ['Switzerland','Qatar','Canada','Bosnia and Herzegovina']                        union all
  select 'C', ['Brazil','Morocco','Scotland','Haiti']                                          union all
  select 'D', ['Australia','Turkey','United States','Paraguay']                                union all
  select 'E', ['Germany','Ecuador','Côte d''Ivoire','Curaçao']                                 union all
  select 'F', ['Netherlands','Japan','Sweden','Tunisia']                                       union all
  select 'G', ['Belgium','Iran','Egypt','New Zealand']                                         union all
  select 'H', ['Spain','Uruguay','Saudi Arabia','Cabo Verde']                                  union all
  select 'I', ['France','Senegal','Norway','Iraq']                                             union all
  select 'J', ['Argentina','Austria','Algeria','Jordan']                                       union all
  select 'K', ['Portugal','Colombia','Uzbekistan','Congo DR']                                  union all
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
Eight games crossed the marquee threshold (both teams above 50% to advance). Three stand out:

- **Norway vs France (Group I, June 26).** λ_home 2.59, λ_away 2.61 — the most evenly matched lambdas on the slate. The model gives France about a 44% chance to win and Norway about a 40%, with the rest a draw. Whoever loses likely finishes second and inherits a tougher knockout draw.
- **Colombia vs Portugal (Group K, June 27).** Portugal favored 47/19/34 with the higher λ (2.33 vs 1.65), but Colombia at 61% top-2 is already a contender — this is the model's best guess at who tops Group K.
- **Scotland vs Brazil (Group C, June 24).** The model gives Brazil about a 47% chance, with 25% to Scotland — surprising upside for a team most punters would write off. The reason: Brazil's λ at 1.95 is lower than every other top-five favorite's home λ in their respective marquee fixtures. If the model is right about Scotland's defense, this is the kind of upset the bracket has been quietly waiting for.
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
The team the model loves that you should probably doubt: **Norway**. Norway is sixth in champion probability (6.0%) on the back of recent xG and a manageable group, but it's never reached a World Cup quarter-final. The model weights recent club form heavily, and Norway's recent form is propped up by Erling Haaland — a single-point-of-failure injury risk the model has no way to encode. If Haaland's hamstring decides otherwise, Norway's bracket evaporates fast.

The team the model dismisses that you should watch: **Croatia**. Croatia sits at just 57% top-2 in Group L and under 1% to win the whole thing — but they were finalists in 2018 and bronze in 2022. The model is using post-2022 form data, and an aging Modrić-era midfield doesn't backtest well against a fresh tournament where 35-year-olds remember how to run.
<!-- /agent prose: dark_horses -->

## A word from the model

<!-- agent prose: closing -->
A word from the model: it knows what it doesn't know. It has no player data beyond xG totals, no injury feed, no tactical awareness. It can't see who Haaland or Bellingham hurt their hamstring against. It weights last-10 form heavily, so hot streaks beat pedigree on paper. None of that makes it useless. It does make it an estimate, not a prophecy.
<!-- /agent prose: closing -->

## How the model works

<!-- agent prose: methodology -->
The model is a Poisson goals model with a per-game luck factor, fit on every international match since January 2022 and a current snapshot of FIFA World Ranking points. Each team's expected goals draws on tier-weighted recent form, a goal-mean prior calibrated against FIFA rank within the 48 qualifiers, and a small economic prior (GDP per capita + population). Host nations get a modest home boost only on home turf. The closed-form group-stage 1X2 probabilities come from a two-dimensional truncated-Normal quadrature; the knockout bracket is a 10,000-iteration Monte Carlo. Full model card: [`results/wc2026-predictor/MODEL.md`](../results/wc2026-predictor/MODEL.md).
<!-- /agent prose: methodology -->
