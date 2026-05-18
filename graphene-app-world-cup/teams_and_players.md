---
title: WC2026 — Teams & Top Players
layout: notebook
---

# WC2026 — Teams & Top Players

A snapshot of the 48 qualified nations and the players they bring to North America in summer 2026. Numbers come from the curated DuckDB layer at `data/wc2026.duckdb` — built on World Bank macro data, the official FIFA Men's World Ranking, StatsBomb tournament matches, and aggregated Understat club xG.

---

## The field at a glance

```sql universe
from curated.dim_team_current
select
  count(distinct team_code) as teams,
  count(distinct confederation) as confederations,
  round(avg(fifa_points), 1) as avg_fifa_points,
  round(max(fifa_points), 1) as top_fifa_points
where is_wc2026_qualifier
```

<BigValue data="universe" value="teams" title="Qualified teams" />
<BigValue data="universe" value="confederations" title="Confederations" />
<BigValue data="universe" value="avg_fifa_points" title="Avg FIFA points" />
<BigValue data="universe" value="top_fifa_points" title="Top FIFA points" />

```sql player_universe
from curated.dim_player
select
  count(distinct player_id) as players,
  count(distinct country_code) as countries_with_players
where is_active
```

<BigValue data="player_universe" value="players" title="Candidate players in master" />
<BigValue data="player_universe" value="countries_with_players" title="Countries with player coverage" />

---

## FIFA ranking — the 48 qualifiers, ranked

A single read from `curated.dim_team_current`. Each row carries everything the model needs: FIFA points, latest GDP per capita, latest population, and confederation tag.

```sql qualifiers_ranked
from curated.dim_team_current
select
  fifa_rank,
  team_code,
  team_name,
  confederation,
  fifa_points,
  fifa_rank_change,
  round(gdp_per_capita_usd_latest, 0) as gdp_per_cap_usd,
  round(population_latest / 1000000.0, 2) as pop_millions
where is_wc2026_qualifier
order by fifa_rank
```

<Table data="qualifiers_ranked" title="All 48 WC2026 qualifiers" sortable="true" />

---

## FIFA points distribution by confederation

UEFA brings the bulk of the heavyweights; CONMEBOL is small but ranked-dense; OFC's lone qualifier is the lowest-ranked side in the tournament.

```sql conf_breakdown
from curated.dim_team_current
select
  confederation,
  count(*) as qualifiers,
  round(avg(fifa_points), 1) as avg_fifa_points,
  round(min(fifa_points), 1) as min_fifa_points,
  round(max(fifa_points), 1) as max_fifa_points
where is_wc2026_qualifier
group by confederation
order by avg_fifa_points desc
```

<BarChart
  data="conf_breakdown"
  x="confederation"
  y="avg_fifa_points"
  title="Average FIFA points by confederation"
  sort="avg_fifa_points desc"
  height="320px"
/>

<Table data="conf_breakdown" title="Confederation roll-up" sortable="true" />

---

## Economic context — GDP per capita vs FIFA points

The "rich-country effect" is real but imperfect. Switzerland sits at $104k/cap and ranks 19th; Morocco is ranked 8th on $4k/cap. Football fortune and national wealth correlate, but the residuals are where interesting bets live.

```sql econ_vs_fifa
from curated.dim_team_current
select
  team_code,
  team_name,
  confederation,
  fifa_rank,
  fifa_points,
  round(gdp_per_capita_usd_latest, 0) as gdp_per_cap_usd
where is_wc2026_qualifier and gdp_per_capita_usd_latest is not null
order by fifa_points desc
```

<ScatterChart
  data="econ_vs_fifa"
  x="gdp_per_cap_usd"
  y="fifa_points"
  series="confederation"
  title="GDP per capita ($USD, 2024) vs FIFA ranking points"
  height="420px"
/>

---

## Population muscle — biggest WC2026 markets

```sql pop_top
from curated.dim_team_current
select
  team_code,
  team_name,
  round(population_latest / 1000000.0, 1) as pop_millions,
  fifa_rank
where is_wc2026_qualifier and population_latest is not null
order by pop_millions desc
limit 12
```

<BarChart
  data="pop_top"
  x="team_name"
  y="pop_millions"
  title="Top 12 qualifiers by population (millions, 2024)"
  sort="pop_millions desc"
  height="360px"
/>

---

## Team attack & defense ratings (squad-aggregated club xG)

The composite ratings combine projected XI club xG (Understat) with national tournament xG (StatsBomb). Higher attack = more chance creation per 90; lower defense = fewer expected goals conceded per match.

```sql attack_ratings
from raw.team_attack_ratings
select
  nation,
  squad_players,
  matched_to_club,
  round(attack_rating, 3) as attack_rating,
  round(attack_nat_only, 3) as attack_nat_only,
  round(attack_club_only, 3) as attack_club_only,
  round(creativity_rating, 2) as creativity,
  round(press_intensity, 2) as press_intensity
order by attack_rating desc
limit 20
```

<BarChart
  data="attack_ratings"
  x="nation"
  y="attack_rating"
  title="Top 20 nations by composite attack rating"
  sort="attack_rating desc"
  height="380px"
/>

<Table data="attack_ratings" title="Top 20 attack ratings" sortable="true" />

```sql defense_ratings
from raw.team_defensive_ratings
select
  nation,
  round(defensive_rating, 3) as defensive_rating,
  round(tournament_xga, 3) as tournament_xga,
  round(club_xga_avg, 3) as club_xga_avg,
  club_sample_size
order by defensive_rating
limit 20
```

<BarChart
  data="defense_ratings"
  x="nation"
  y="defensive_rating"
  title="Top 20 nations by defensive rating (lower = better)"
  sort="defensive_rating asc"
  height="380px"
/>

<Table data="defense_ratings" title="Top 20 defenses (lower = better)" sortable="true" />

---

## Form trajectory — 6 favorites across the last 5 years

How the six WC2026 heavyweights have actually moved at major tournaments since 2018. Net xG = `xG − goals conceded` per match — one number that captures both attacking and defensive quality. Above zero = creating more than you allow.

```sql top6_form_long
from raw.statsbomb_team_xg
select
  case team
    when 'Argentina'   then 'Argentina'
    when 'Netherlands' then 'Netherlands'
    when 'Portugal'    then 'Portugal'
    when 'Germany'     then 'Germany'
    when 'France'      then 'France'
    when 'Spain'       then 'Spain'
  end as country,
  competition,
  season,
  max(cast(match_date as date)) as tournament_end,
  count(*) as matches,
  round(sum(xg) / count(*), 2) as xg_per_match,
  round(sum(goals_conceded) / count(*) :: double, 2) as xga_per_match,
  round((sum(xg) - sum(goals_conceded)) / count(*) :: double, 2) as net_xg
where team in ('Argentina', 'Netherlands', 'Portugal', 'Germany', 'France', 'Spain')
group by 1, 2, 3
order by tournament_end
```

```sql top6_form
from top6_form_long
select
  season,
  year(max(tournament_end)) as year,
  max(case when country = 'Argentina'   then net_xg end) as Argentina,
  max(case when country = 'Spain'       then net_xg end) as Spain,
  max(case when country = 'France'      then net_xg end) as France,
  max(case when country = 'Portugal'    then net_xg end) as Portugal,
  max(case when country = 'Netherlands' then net_xg end) as Netherlands,
  max(case when country = 'Germany'     then net_xg end) as Germany
group by season
order by year
```

<LineChart
  data="top6_form"
  x="year"
  y="Argentina, Spain, France, Portugal, Netherlands, Germany"
  title="Net xG per match — major tournament form 2018 → 2024"
  height="460px"
/>

```sql top6_attack
from top6_form_long
select
  season,
  year(max(tournament_end)) as year,
  max(case when country = 'Argentina'   then xg_per_match end) as Argentina,
  max(case when country = 'Spain'       then xg_per_match end) as Spain,
  max(case when country = 'France'      then xg_per_match end) as France,
  max(case when country = 'Portugal'    then xg_per_match end) as Portugal,
  max(case when country = 'Netherlands' then xg_per_match end) as Netherlands,
  max(case when country = 'Germany'     then xg_per_match end) as Germany
group by season
order by year
```

<LineChart
  data="top6_attack"
  x="year"
  y="Argentina, Spain, France, Portugal, Netherlands, Germany"
  title="Attacking output — xG per match"
  height="400px"
/>

```sql top6_defense
from top6_form_long
select
  season,
  year(max(tournament_end)) as year,
  max(case when country = 'Argentina'   then xga_per_match end) as Argentina,
  max(case when country = 'Spain'       then xga_per_match end) as Spain,
  max(case when country = 'France'      then xga_per_match end) as France,
  max(case when country = 'Portugal'    then xga_per_match end) as Portugal,
  max(case when country = 'Netherlands' then xga_per_match end) as Netherlands,
  max(case when country = 'Germany'     then xga_per_match end) as Germany
group by season
order by year
```

<LineChart
  data="top6_defense"
  x="year"
  y="Argentina, Spain, France, Portugal, Netherlands, Germany"
  title="Defensive output — goals conceded per match (lower = better)"
  height="400px"
/>

**What the chart tells us:**
- 🇦🇷 **Argentina** is the only team on a clean upward arc: −0.85 net xG at WC2018 → +1.86 at WC2022 → +2.51 at Copa 2024. They went from over-conceding to one of the strongest net-attacking sides in the dataset.
- 🇵🇹 **Portugal** had a quiet 2018–2022 (around zero) and then exploded at Euro 2024 to +2.34 net xG. Whether that's a real step-change or a small-sample spike is the question for 2026.
- 🇪🇸 **Spain** peaked at **+2.67 at Euro 2020** and has slowly declined to +0.94 at Euro 2024 — even though they won the trophy. Their xG dropped from 3.67/match to 1.51/match. They are converting better than they create.
- 🇫🇷 **France** is the most consistent: net xG between +0.4 and +1.5 every tournament. No collapse, no spike. A model favorite for being unsurprising.
- 🇩🇪 **Germany** had its Euro 2020 wobble (−0.22 net xG) and has recovered to around +1.0 since. Still the lowest variance ceiling of the group.
- 🇳🇱 **Netherlands** is the only one of the six with a clear *downward* trajectory: +1.21 (Euro 2020) → +0.98 (WC 2022) → +0.05 (Euro 2024). At Euro 2024 they were essentially neutral.

```sql top6_form_table
from top6_form_long
select country, season, tournament_end, matches, xg_per_match, xga_per_match, net_xg
order by country, tournament_end
```

<Table data="top6_form_table" title="Per-tournament numbers" sortable="true" />

---

## Team xG output across recent tournaments

Tournament-level xG and xGA aggregated from per-match StatsBomb data across WC2018, WC2022, Euro2020, Euro2024, and Copa América 2024. Only teams with **3+ matches** in the dataset shown.

```sql team_tourney_xg
from raw.statsbomb_team_xg
select
  team,
  count(*) as matches,
  sum(goals) as goals_for,
  sum(goals_conceded) as goals_against,
  round(sum(xg), 2) as total_xg,
  round(sum(xg) / count(*), 2) as xg_per_match,
  round(sum(goals_conceded) / count(*) :: DOUBLE, 2) as ga_per_match
group by team
having count(*) >= 3
order by xg_per_match desc
limit 20
```

<BarChart
  data="team_tourney_xg"
  x="team"
  y="xg_per_match"
  title="Top 20 teams by xG per tournament match"
  sort="xg_per_match desc"
  height="400px"
/>

<Table data="team_tourney_xg" title="Tournament xG / xGA roll-up" sortable="true" />

---

## Top goalscoring threats — combined xG across club & country

Top players ordered by cross-source xG (StatsBomb international + Understat club). The `dim_player` master ensures one row per real human even when sources spell the name differently.

```sql top_xg_players
from curated.fact_player_xg
select
  dim_player.display_name as player,
  dim_player.country_code as country,
  dim_player.position as position,
  round(total_xg, 1) as total_xg,
  total_goals,
  round(total_goals - total_xg, 1) as goal_minus_xg,
  total_minutes,
  total_shots
order by total_xg desc
limit 20
```

<BarChart
  data="top_xg_players"
  x="player"
  y="total_xg"
  title="Top 20 attackers by combined xG"
  sort="total_xg desc"
  height="420px"
/>

<Table data="top_xg_players" title="Top 20 attackers — xG, goals, and luck residual (goals − xG)" sortable="true" />

---

## The lucky finishers — biggest positive `goals − xG`

Players who consistently outscore their xG. Either elite finishing skill, small-sample luck, or both. The model should regress these toward xG when projecting future matches.

```sql lucky_finishers
from curated.fact_player_xg
select
  dim_player.display_name as player,
  dim_player.country_code as country,
  dim_player.position as position,
  round(total_xg, 1) as total_xg,
  total_goals,
  round(total_goals - total_xg, 1) as goals_above_xg,
  total_minutes
where total_xg >= 5
order by goals_above_xg desc
limit 15
```

<BarChart
  data="lucky_finishers"
  x="player"
  y="goals_above_xg"
  title="Top 15 over-performers — goals above expected"
  sort="goals_above_xg desc"
  height="380px"
/>

<Table data="lucky_finishers" title="Goals above xG (min 5 xG)" sortable="true" />

---

## Creators — top playmakers by xA

```sql top_xa_players
from curated.fact_player_xg
select
  dim_player.display_name as player,
  dim_player.country_code as country,
  dim_player.position as position,
  round(total_xa, 1) as total_xa,
  total_minutes
where total_xa >= 1
order by total_xa desc
limit 15
```

<BarChart
  data="top_xa_players"
  x="player"
  y="total_xa"
  title="Top 15 creators by total xA"
  sort="total_xa desc"
  height="380px"
/>

<Table data="top_xa_players" title="Top playmakers (xA)" sortable="true" />

---

## Country-level attacking firepower — top xG by national team

xG totals rolled up by national team (only counts rows tagged with a `team_code`, i.e. tournament minutes — club rows are excluded so we see real international attacking output).

```sql country_xg
from curated.fact_player_xg
select
  dim_team.team_code as team_code,
  dim_team.team_name as team_name,
  round(sum(xg_total), 1) as nat_team_xg,
  sum(goals) as nat_team_goals,
  count(distinct player_id) as scorers
where team_code is not null
group by 1, 2
having sum(xg_total) >= 1
order by nat_team_xg desc
limit 20
```

<BarChart
  data="country_xg"
  x="team_name"
  y="nat_team_xg"
  title="Top 20 national teams by aggregated international xG"
  sort="nat_team_xg desc"
  height="400px"
/>

<Table data="country_xg" title="National-team xG roll-up" sortable="true" />

---

## Per-country squad coverage

Coverage of the player master across qualifying nations. Higher numbers ≈ more developed data signal for the model.

```sql per_country_coverage
from curated.dim_player
select country_code, player_count
where is_active
order by player_count desc
limit 25
```

<BarChart
  data="per_country_coverage"
  x="country_code"
  y="player_count"
  title="Players in dim_player by country (top 25)"
  sort="player_count desc"
  height="320px"
/>

---

*Built from `data/wc2026.duckdb`. Refresh with `python3 tools/build_duckdb.py` then `npx graphene check` to validate.*
