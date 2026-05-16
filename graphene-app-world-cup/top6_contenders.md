---
title: WC2026 — Top 6 Contenders
layout: notebook
---

# The Top 6 Contenders for WC2026

Six teams to watch heading into the 2026 World Cup. Five of them are picked by the data — the highest Contender Scores in the field. The sixth, the **Netherlands**, is included as the highest-ranked qualifier outside the top 5 by current FIFA points and a perennial top-10 contender worth tracking even when recent form has dipped.

The same simple methodology runs across all six: three components, each scored on a 0–100 percentile within the 48 WC2026 qualifiers, then averaged into a single **Contender Score**.

1. **Attack** — expected goals (xG) created per match across the team's last two major tournaments.
2. **Defense** — goals conceded per match across those same matches (inverted: lower = better).
3. **Pedigree** — current FIFA Men's World Ranking points (April 2026 edition).

---

## The recent form pool

Each team's last two major tournaments — WC2022, Euro 2020/2024, Copa América 2024.

```sql recent_form
with name_map as (
  select 'Argentina' as sb_name, 'ARG' as team_code union all
  select 'Spain','ESP' union all select 'France','FRA' union all
  select 'Germany','GER' union all select 'Netherlands','NED' union all
  select 'Portugal','POR' union all select 'Brazil','BRA' union all
  select 'England','ENG' union all select 'Belgium','BEL' union all
  select 'Croatia','CRO' union all select 'Morocco','MAR' union all
  select 'Italy','ITA' union all select 'Colombia','COL' union all
  select 'Senegal','SEN' union all select 'Mexico','MEX' union all
  select 'United States','USA' union all select 'Uruguay','URU' union all
  select 'Japan','JPN' union all select 'Switzerland','SUI' union all
  select 'IR Iran','IRI' union all
  select 'Ecuador','ECU' union all select 'Canada','CAN' union all
  select 'Australia','AUS' union all select 'Korea Republic','KOR'
),
per_tournament as (
  select n.team_code, t.competition, t.season,
         count(*) as matches,
         sum(t.xg) as xg_total,
         sum(t.goals_conceded) as ga_total,
         max(cast(t.match_date as date)) as last_match
  from raw.statsbomb_team_xg t
  inner join name_map n on t.team = n.sb_name
  group by 1, 2, 3
),
ranked as (
  select team_code, competition, season, matches, xg_total, ga_total, last_match,
         row_number() over (partition by team_code order by last_match desc) as recency
  from per_tournament
)
select team_code,
       sum(matches) as recent_matches,
       round(sum(xg_total) / sum(matches), 2) as xg_per_match,
       round(sum(ga_total) / sum(matches) :: double, 2) as ga_per_match,
       round((sum(xg_total) - sum(ga_total)) / sum(matches) :: double, 2) as net_xg_per_match
from ranked
where recency <= 2
group by team_code
```

## Contender Score across all 48 qualifiers

```sql contenders
from recent_form
inner join curated.dim_team_current d on d.team_code = recent_form.team_code
select
  d.team_code,
  d.team_name,
  d.confederation,
  d.fifa_rank,
  d.fifa_points,
  d.gdp_per_capita_usd_latest,
  d.population_latest,
  recent_matches,
  xg_per_match,
  ga_per_match,
  net_xg_per_match,
  round(100 * percent_rank() over (order by xg_per_match), 1)         as attack_score,
  round(100 * percent_rank() over (order by ga_per_match desc), 1)    as defense_score,
  round(100 * percent_rank() over (order by d.fifa_points), 1)        as pedigree_score,
  round((
    percent_rank() over (order by xg_per_match) +
    percent_rank() over (order by ga_per_match desc) +
    percent_rank() over (order by d.fifa_points)
  ) * 100.0 / 3.0, 1) as contender_score
where d.is_wc2026_qualifier
order by contender_score desc
```

---

## The Top 6

```sql top6
from contenders
select team_code, team_name, confederation, contender_score,
       attack_score, defense_score, pedigree_score,
       xg_per_match, ga_per_match, net_xg_per_match, fifa_rank
where team_code in ('BRA','ARG','FRA','ESP','POR','NED')
order by contender_score desc
```

<Table data="top6" title="The Top 6 Contenders" sortable="true" />

<BarChart
  data="top6"
  x="team_name"
  y="contender_score"
  title="Top 6 Contender Scores (0–100)"
  sort="contender_score desc"
  height="380px"
  label="true"
/>

### Score breakdown — each component side by side

```sql top6_components
from top6
select team_name, attack_score, defense_score, pedigree_score
order by team_name
```

<BarChart
  data="top6_components"
  x="team_name"
  y="attack_score, defense_score, pedigree_score"
  arrange="group"
  title="Top 6 — score breakdown (Attack | Defense | Pedigree, 0–100)"
  height="380px"
/>

---

## Why each team is in the Top 6

### 🇧🇷 Brazil — Contender Score **90.0**
The defensive masters. **2.57 xG created, 0.56 goals conceded per match** across 9 recent matches — the stingiest defense of any WC2026 qualifier. FIFA #6 lags behind their underlying numbers, marking them as a classic regression-to-the-mean candidate. Best pure-numbers profile in the field.

### 🇦🇷 Argentina — Contender Score **86.7**
The reigning. WC2022 winners + Copa América 2024 winners. **2.85 xG/match** is the highest in the field — they create chances better than anyone right now. Defense (0.69 conceded) is solid but not Brazil-level. Pedigree (90/100) reflects the trophy haul.

### 🇫🇷 France — Contender Score **78.3**
Top-3 in every component, FIFA #1 in the world. **2.08 xG, 0.85 conceded** is unspectacular individually but no holes anywhere. The lowest-variance bet of the six — a model favourite specifically because they are unsurprising.

### 🇪🇸 Spain — Contender Score **75.0**
Euro 2024 champions. **1.61 xG/match (45/100)** is mid-pack — they win on **defense (85/100)** and **pedigree (95/100, FIFA #2)**. Finishing has been doing the lifting. The risk: regression toward their xG would hurt.

### 🇵🇹 Portugal — Contender Score **73.3**
The Euro 2024 surge moved them up. **2.20 xG/match** is the second-best attack in the top 6. Defense is the weakest of the contenders (50/100, 0.90 conceded). Biggest swing factor of the top 6 — they could win deep, or exit early.

### 🇳🇱 Netherlands — Contender Score **45.0** (FIFA #7 wildcard)
Included because they're the next-best non-top-5 in FIFA points, with the pedigree (70/100) of a perennial contender. But the underlying numbers are softer: attack 30/100 and defense 35/100 are both bottom-half of the field. Their net xG fell from +1.21 at Euro 2020 to +0.05 at Euro 2024. Most likely to win a knockout game on the day; least likely to lift the trophy across seven matches.

---

## Economic context — wealth vs football

Where do these six come from in raw economic terms? The chart sits below the football data — and the relationship is genuinely surprising.

```sql econ_context
from contenders
select
  team_code,
  team_name,
  confederation,
  fifa_rank,
  round(fifa_points, 0) as fifa_pts,
  round(gdp_per_capita_usd_latest, 0) as gdp_per_cap_usd,
  round(population_latest / 1000000.0, 1) as pop_millions,
  round(fifa_points / (population_latest / 1000000.0), 1) as fifa_points_per_million,
  round(fifa_points * 1000.0 / gdp_per_capita_usd_latest, 1) as fifa_per_1k_gdp_pc
where team_code in ('BRA', 'ARG', 'FRA', 'ESP', 'POR', 'NED')
order by fifa_rank
```

<Table data="econ_context" title="Economic profile of the Top 6" sortable="true" />

### Football production per capita

How much football does each nation produce per inhabitant? Portugal blows the field away — 10.7M people producing FIFA #5 standing.

```sql per_capita
from econ_context
select team_name, fifa_points_per_million
order by fifa_points_per_million desc
```

<BarChart
  data="per_capita"
  x="team_name"
  y="fifa_points_per_million"
  title="FIFA points per million people"
  sort="fifa_points_per_million desc"
  height="360px"
  label="true"
/>

### Football vs economy

Football "punch" relative to GDP per capita. A high number means a country produces more football than its economy alone would predict. Brazil and Argentina dominate here — and they sit 1–2 in Contender Score. Wealth doesn't buy football.

```sql per_gdp
from econ_context
select team_name, fifa_per_1k_gdp_pc
order by fifa_per_1k_gdp_pc desc
```

<BarChart
  data="per_gdp"
  x="team_name"
  y="fifa_per_1k_gdp_pc"
  title="FIFA points per $1k of GDP per capita (football overperformance vs economy)"
  sort="fifa_per_1k_gdp_pc desc"
  height="360px"
  label="true"
/>

### GDP per capita trajectory 2020 → 2024

```sql gdp_trajectory_long
from curated.fact_team_economics
select team_code, year, gdp_per_capita_usd
where team_code in ('BRA','ARG','FRA','ESP','POR','NED')
  and year between 2020 and 2024
  and gdp_per_capita_usd is not null
order by year
```

```sql gdp_trajectory
from gdp_trajectory_long
select
  cast(year as varchar) as year_label,
  max(case when team_code = 'BRA' then gdp_per_capita_usd end) as Brazil,
  max(case when team_code = 'ARG' then gdp_per_capita_usd end) as Argentina,
  max(case when team_code = 'FRA' then gdp_per_capita_usd end) as France,
  max(case when team_code = 'ESP' then gdp_per_capita_usd end) as Spain,
  max(case when team_code = 'POR' then gdp_per_capita_usd end) as Portugal,
  max(case when team_code = 'NED' then gdp_per_capita_usd end) as Netherlands
group by year_label
order by year_label
```

<LineChart
  data="gdp_trajectory"
  x="year_label"
  y="Brazil, Argentina, France, Spain, Portugal, Netherlands"
  title="GDP per capita (USD) — 2020 to 2024"
  height="420px"
/>

**What the chart says:**
- 🇳🇱 Netherlands +26% nominal growth ($53k → $68k) — the football data hasn't caught up to this prosperity.
- 🇫🇷 France and 🇪🇸 Spain grew steadily — the football performance roughly matches the economic baseline.
- 🇵🇹 Portugal modest economy ($22k → $29k), elite football performance.
- 🇦🇷 Argentina the surprise — +64% nominal growth in 5 years amid trophy-winning football. Economy volatile but trending up.
- 🇧🇷 Brazil the flattest grower ($7k → $10k) — and pedigree has slipped (now FIFA #6). The football is recovering faster than the economy.

The headline: **football performance and economic prosperity don't track each other in this sample.** If anything, the relationship is inverse — the two poorest nations of the six (Brazil, Argentina) lead the Contender Score, the wealthiest (Netherlands) trails. Football culture, not capital, is doing the heavy lifting.

---

## Honest caveats

- **xG is for shots, not penalty shootouts.** Argentina won both WC2022 and Copa 2024 with last-gasp moments and shootout wins; that "clutch factor" isn't in the model.
- **No luck factor yet.** A team's actual goal output is the deterministic xG number plus noise. The simulation that adds a random-luck variable per match will spread these probabilities and let upsets land more realistically.
- **No injury / squad-change weighting.** A retirement or a major injury between now and June 2026 isn't reflected here.
- **No home-field advantage.** Mexico, USA and Canada all get a structural boost in a real model — they currently sit outside the top 6 on pure form numbers.
- **Pedigree is a 24-month rolling proxy, not history.** Argentina's 2022 World Cup is baked in; their 1986 win is not.

The next model iteration adds a Monte Carlo luck-factor loop on top of these scores, turning "Argentina is best on the numbers" into "Argentina wins 18% of simulated tournaments, France 14%, Brazil 12%, …" — which is the probability the model actually outputs.
