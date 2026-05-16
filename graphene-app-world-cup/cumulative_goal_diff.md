---
title: Cumulative goal differential — last 12 months
layout: notebook
---

# Cumulative goal differential — last 12 months

Six contenders, one year of international football (2025-05-15 → 2026-05-15). Each line is the running sum of (goals for − goals against) over time. Step up = positive-GD match; step down = deficit. **Slope is form.**

Every value is reproducible against `curated.fact_international_match`.

---

## Per-match cumulative — long form

```sql cumulative_long
with t6 as (
  select 'ARG' as tc, 'Argentina'   as team_name union all
  select 'BRA',        'Brazil'                  union all
  select 'ESP',        'Spain'                   union all
  select 'FRA',        'France'                  union all
  select 'GER',        'Germany'                 union all
  select 'NED',        'Netherlands'
),
team_matches as (
  select f.match_date, t6.tc, t6.team_name,
         case when f.home_team_code = t6.tc
              then f.home_score - f.away_score
              else f.away_score - f.home_score
         end as gd
  from curated.fact_international_match f
  inner join t6 on t6.tc in (f.home_team_code, f.away_team_code)
  where f.match_date between date '2025-05-15' and date '2026-05-15'
)
from team_matches
select match_date,
       tc as team_code,
       team_name,
       gd,
       sum(gd) over (partition by tc order by match_date
                     rows between unbounded preceding and current row) as cum_gd
order by team_code, match_date
```

## The chart — six trajectories, end-of-month

For each team, take the cumulative GD at its **last match of each calendar month** (using `arg_max` against `match_date`). Forward-fill across months a team didn't play, then pivot wide — one column per team.

```sql cumulative_wide
with monthly as (
  from cumulative_long
  select date_trunc('month', match_date) as month,
         team_code,
         arg_max(cum_gd, match_date) as cum_gd
  group by date_trunc('month', match_date), team_code
),
months as (
  select distinct month from monthly
),
teams as (
  select 'ARG' as tc union all select 'BRA' union all select 'ESP'
  union all select 'FRA' union all select 'GER' union all select 'NED'
),
grid as (
  select months.month, teams.tc
  from months cross join teams
),
joined as (
  select grid.month, grid.tc, monthly.cum_gd
  from grid
  left join monthly
    on monthly.team_code = grid.tc
   and monthly.month = grid.month
),
counted as (
  from joined
  select month, tc, cum_gd,
         count(cum_gd) over (partition by tc order by month
                             rows between unbounded preceding and current row) as grp
),
filled as (
  from counted
  select month, tc,
         max(cum_gd) over (partition by tc, grp) as cum_gd
)
from filled
select month,
       max(case when tc = 'NED' then coalesce(cum_gd, 0) end) as Netherlands,
       max(case when tc = 'ESP' then coalesce(cum_gd, 0) end) as Spain,
       max(case when tc = 'FRA' then coalesce(cum_gd, 0) end) as France,
       max(case when tc = 'GER' then coalesce(cum_gd, 0) end) as Germany,
       max(case when tc = 'BRA' then coalesce(cum_gd, 0) end) as Brazil,
       max(case when tc = 'ARG' then coalesce(cum_gd, 0) end) as Argentina
group by month
order by month
```

<LineChart
  data="cumulative_wide"
  x="month"
  y="Netherlands, Spain, France, Germany, Brazil, Argentina"
  title="Cumulative goal differential by month — May 2025 → May 2026"
  height="480px"
/>

---

## Year-end snapshot

Where each team finishes the 12-month window.

```sql final_gd
from cumulative_long
select team_name,
       team_code,
       arg_max(cum_gd, match_date) as final_cum_gd,
       count(*) as matches,
       max(match_date) as last_match
group by team_code, team_name
order by final_cum_gd desc
```

<BarChart
  data="final_gd"
  x="team_name"
  y="final_cum_gd"
  title="12-month cumulative goal differential"
  sort="final_cum_gd desc"
  height="320px"
  label="true"
/>

<Table data="final_gd" title="Final cumulative GD, matches played, last match date" sortable="true" />
