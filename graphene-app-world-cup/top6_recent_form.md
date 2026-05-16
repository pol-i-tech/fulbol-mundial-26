---
title: WC2026 Top 6 — Recent Form
layout: notebook
---

# WC2026 Top 6 — what the last 10 internationals say

Six teams to watch. Five picked by the model's Contender Score (Brazil, Argentina, France, Spain, Portugal); the sixth — **Netherlands** — included because the data after Euro 2024 tells a very different story than the data before it.

Below: each team's **last 10 internationals**, the headline goal-difference and win counts, the Netherlands run match by match, the tournament xG that underpins the model, and the economic context for completeness. Every number is reproducible against `curated.fact_international_match` and `raw.statsbomb_team_xg`.

---

## Last 10 internationals — the form snapshot

```sql last10_form
with t6 as (
  select 'BRA' as tc, 'Brazil' as team_name union all
  select 'ARG', 'Argentina' union all
  select 'FRA', 'France' union all
  select 'ESP', 'Spain' union all
  select 'POR', 'Portugal' union all
  select 'NED', 'Netherlands'
),
team_view as (
  select f.match_date, t6.tc as team_code, t6.team_name,
         case when f.home_team_code = t6.tc then f.home_score else f.away_score end as gf,
         case when f.home_team_code = t6.tc then f.away_score else f.home_score end as ga,
         case
           when f.home_team_code = t6.tc and f.home_score > f.away_score then 'W'
           when f.away_team_code = t6.tc and f.away_score > f.home_score then 'W'
           when f.home_score = f.away_score then 'D' else 'L'
         end as result
  from curated.fact_international_match f
  inner join t6 on t6.tc in (f.home_team_code, f.away_team_code)
),
ranked as (
  select team_view.*,
         row_number() over (partition by team_code order by match_date desc) as rn
  from team_view
)
from ranked
select team_name,
       count(*) as matches,
       sum(case when result = 'W' then 1 else 0 end) as wins,
       sum(case when result = 'D' then 1 else 0 end) as draws,
       sum(case when result = 'L' then 1 else 0 end) as losses,
       sum(gf) as goals_for,
       sum(ga) as goals_against,
       sum(gf) - sum(ga) as goal_diff,
       min(match_date) as from_date,
       max(match_date) as to_date
where rn <= 10
group by team_name
order by losses asc, goal_diff desc
```

<Table data="last10_form" title="Last 10 internationals per team — wins, draws, losses, goals" sortable="true" />

---

## Who's piling up the goal difference?

```sql last10_gd
from last10_form
select team_name, goal_diff
order by goal_diff desc
```

<BarChart
  data="last10_gd"
  x="team_name"
  y="goal_diff"
  title="Goal differential in last 10 internationals"
  sort="goal_diff desc"
  height="320px"
  label="true"
/>

🇳🇱 Netherlands tops the field at **+24** — better than Spain's +23 and Portugal's +19. The two Contender-Score leaders (Brazil, Argentina) are at the bottom of this chart, the second story of the page.

---

## Who's actually winning the most?

```sql last10_wins
from last10_form
select team_name, wins, draws, losses
order by wins desc, losses asc
```

<BarChart
  data="last10_wins"
  x="team_name"
  y="wins"
  title="Wins in last 10 internationals"
  sort="wins desc"
  height="300px"
  label="true"
/>

France leads on wins (8), but the **three teams that haven't lost a match in 10 internationals**:

- 🇳🇱 Netherlands — 7W 3D 0L
- 🇪🇸 Spain — 7W 3D 0L
- (next closest: Portugal 6W 3D 1L)

---

## The Netherlands run — every match, in order

This is the heart of the page. 10 matches, zero losses, 30 goals scored, 6 conceded. The 8-0 against Malta is a small-sample outlier but the 4-0 wins against Finland and Lithuania, and the 2-1 over Norway, are clean WC-qualification dominance.

```sql ned_last10
with team_view as (
  select f.match_date,
         case when f.home_team_code = 'NED' then f.away_team_code else f.home_team_code end as opponent,
         case when f.home_team_code = 'NED' then f.home_score else f.away_score end as gf,
         case when f.home_team_code = 'NED' then f.away_score else f.home_score end as ga,
         case
           when f.home_team_code = 'NED' and f.home_score > f.away_score then 'W'
           when f.away_team_code = 'NED' and f.away_score > f.home_score then 'W'
           when f.home_score = f.away_score then 'D' else 'L'
         end as result,
         f.tournament
  from curated.fact_international_match f
  where f.home_team_code = 'NED' or f.away_team_code = 'NED'
),
ranked as (
  select team_view.*,
         row_number() over (order by match_date desc) as rn
  from team_view
)
from ranked
select match_date, opponent, gf, ga, result, tournament
where rn <= 10
order by match_date desc
```

<Table data="ned_last10" title="Netherlands — last 10 international matches" sortable="true" />

```sql ned_running_gd
from ned_last10
select match_date, sum(gf - ga) over (order by match_date) as cumulative_goal_diff
order by match_date
```

<LineChart
  data="ned_running_gd"
  x="match_date"
  y="cumulative_goal_diff"
  title="Netherlands cumulative goal differential (June 2025 → March 2026)"
  height="320px"
/>

---

## The xG view — what the model "sees" (last 2 major tournaments)

Where the Contender Score was built — recent xG and goals conceded at WC2022, Euro 2020/2024, and Copa América 2024. This is why Brazil and Argentina rank #1–2 in the model.

```sql tourney_xg
with t6 as (
  select 'Brazil' as sb, 'BRA' as tc union all
  select 'Argentina','ARG' union all
  select 'France','FRA' union all
  select 'Spain','ESP' union all
  select 'Portugal','POR' union all
  select 'Netherlands','NED'
),
per_tournament as (
  select t6.tc, t6.sb,
         count(*) as matches,
         sum(t.xg) as xg_total,
         sum(t.goals_conceded) as ga_total,
         max(cast(t.match_date as date)) as last_match
  from raw.statsbomb_team_xg t
  inner join t6 on t.team = t6.sb
  group by t6.tc, t6.sb, t.competition, t.season
),
ranked as (
  select per_tournament.*, row_number() over (partition by tc order by last_match desc) as recency
  from per_tournament
)
from ranked
select sb as team_name,
       round(sum(xg_total) / sum(matches), 2) as xg_per_match,
       round(sum(ga_total) / sum(matches) :: double, 2) as ga_per_match,
       round((sum(xg_total) - sum(ga_total)) / sum(matches) :: double, 2) as net_xg_per_match
where recency <= 2
group by sb
order by xg_per_match desc
```

<BarChart
  data="tourney_xg"
  x="team_name"
  y="xg_per_match"
  title="xG created per match (last 2 major tournaments)"
  sort="xg_per_match desc"
  height="320px"
  label="true"
/>

<BarChart
  data="tourney_xg"
  x="team_name"
  y="ga_per_match"
  title="Goals conceded per match (last 2 major tournaments — lower = better)"
  sort="ga_per_match asc"
  height="300px"
  label="true"
/>

---

## Economic context

Where these six come from in macro terms — GDP per capita, population, FIFA rank. The takeaway: **football performance does not track wealth**. The two best teams by the xG model (Brazil, Argentina) are the two poorest economies of the group. The wealthiest (Netherlands, $68k/cap) has the form to match it now.

```sql econ_snapshot
from curated.dim_team_current
inner join (select 'BRA' as tc union all select 'ARG' union all select 'FRA'
            union all select 'ESP' union all select 'POR' union all select 'NED') t6
        on t6.tc = dim_team_current.team_code
select team_code, team_name, confederation, fifa_rank,
       round(fifa_points, 0) as fifa_pts,
       round(gdp_per_capita_usd_latest, 0) as gdp_per_cap_usd,
       round(population_latest / 1000000.0, 1) as pop_millions
order by fifa_rank
```

<Table data="econ_snapshot" title="Economic + FIFA profile of the Top 6" sortable="true" />

---

## The conclusion — model vs recent form

Two lenses, two different reads. The model (Contender Score, based on **major tournaments**) likes Brazil and Argentina. The form lens (last 10 internationals) flips the picture: 🇳🇱 Netherlands lead on goal differential, and 🇧🇷 Brazil — best on xG — has actually **lost 3 of their last 10**.

The honest read: Brazil and Argentina remain the underlying-numbers favorites, but the **Netherlands renaissance after Euro 2024 is real and the model is a tournament-window behind in catching it**. By June 2026, one of these two readings will be vindicated.

The next iteration of the model will weight recent international form alongside major-tournament xG, so the Netherlands story moves from "missed" to "tracked".
