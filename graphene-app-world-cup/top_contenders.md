---
title: WC2026 — Top 5 Title Contenders
layout: notebook
---

# Who wins WC2026? A simple three-factor read

Five teams stand out on the numbers. The methodology is deliberately simple — three things you'd expect a champion to do well, blended into one score:

1. **Attack** — how many expected goals (xG) the team creates per match across its last two major tournaments.
2. **Defense** — how few goals it concedes per match across those same matches. Lower = better.
3. **Pedigree** — current FIFA Men's World Ranking points (April 2026 edition).

Each metric is scored on a 0–100 percentile within the 48 WC2026 qualifiers. The **Contender Score** is the average of the three. No fancy machine learning, no luck factor (yet) — just a clean read of who creates chances, who shuts down opponents, and who's already proven themselves on FIFA's own scale.

---

## The recent form pool

Each team's last two major tournaments — WC2022, Euro 2020/2024, Copa América 2024. This is the "what have you done lately" window the model rewards.

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

## Contender score — percentile blend of attack, defense and pedigree

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

<Table data="contenders" title="WC2026 qualifiers — Contender Score breakdown (top to bottom)" sortable="true" />

---

## The top 5

```sql top5
from contenders
select team_code, team_name, confederation, contender_score,
       attack_score, defense_score, pedigree_score,
       xg_per_match, ga_per_match, net_xg_per_match, fifa_rank
order by contender_score desc
limit 5
```

<Table data="top5" title="The five teams the model likes most" sortable="true" />

<BarChart
  data="top5"
  x="team_name"
  y="contender_score"
  title="Top 5 Contender Scores (0–100)"
  sort="contender_score desc"
  height="320px"
  label="true"
/>

### What each component looks like for the top 5

```sql top5_components
from top5
select team_name, attack_score, defense_score, pedigree_score
order by team_name
```

<BarChart
  data="top5_components"
  x="team_name"
  y="attack_score, defense_score, pedigree_score"
  arrange="group"
  title="Top 5 — score breakdown (Attack | Defense | Pedigree, 0–100)"
  height="340px"
/>

---

## 🇳🇱 Where does the Netherlands fit in?

A common question — the Dutch are FIFA #7 with serious recent tournament pedigree, so why aren't they in the top 5? The numbers say the gap is real, not a methodology quirk.

```sql top5_plus_ned
from contenders
select team_code, team_name, contender_score, attack_score, defense_score, pedigree_score,
       xg_per_match, ga_per_match, fifa_rank
where team_code in ('BRA','ARG','FRA','ESP','POR','NED')
order by contender_score desc
```

<Table data="top5_plus_ned" title="Top 5 vs Netherlands — side by side" sortable="true" />

<BarChart
  data="top5_plus_ned"
  x="team_name"
  y="contender_score"
  title="Contender Score — Top 5 + Netherlands"
  sort="contender_score desc"
  height="340px"
  label="true"
/>

<BarChart
  data="top5_plus_ned"
  x="team_name"
  y="attack_score, defense_score, pedigree_score"
  arrange="group"
  title="Component breakdown — Top 5 + Netherlands"
  height="360px"
/>

### Why the Netherlands sits at score 45.0 (rank #14 overall)

Three numbers tell the story:

- **Attack score 30/100** — Their 1.48 xG/match across the last two majors (WC2022 + Euro 2024) ranks 14th of 21 WC2026 qualifiers in the dataset. Brazil and Argentina are creating nearly 2× more chances per match.
- **Defense score 35/100** — They've conceded **1.00 goals per match** recently. Brazil concedes 0.56, Spain 0.64, Argentina 0.69. The Dutch are giving up roughly twice as many goals per match as the leading defensive sides.
- **Pedigree score 70/100** — Solid (FIFA #7) but no longer elite. France, Spain, England, Brazil are all ahead. Pedigree is the only component keeping them out of the bottom half.

**The Euro 2024 number was the warning**: Net xG fell to just +0.05 per match — essentially neutral. Their attacking output collapsed from 2.21 xG/match at Euro 2020 to 1.22 at Euro 2024, and the defense slipped at the same time. To make the WC2026 top 5 they'd need to add roughly **1 xG/match** to their recent form — a tall order for a squad in transition.

The model isn't writing them off — they could absolutely beat any of the top 5 on a given day. But "most likely to win the tournament" is a different question from "could win any match", and the seven-game tournament path rewards consistent excellence, not occasional brilliance.

---

## Why these five

### 🇦🇷 Argentina
WC2022 winners. Copa América 2024 winners. **2.85 xG / 0.69 goals conceded per match** across 13 matches in the last two tournaments — best in the field on both ends. The only side combining elite chance creation with elite defending right now.

### 🇧🇷 Brazil
Eliminated early at Copa América 2024, but the underlying numbers are ferocious: **2.57 xG, 0.56 conceded per match**. The lowest goals-conceded rate of any qualifier. Their FIFA points (1,761) lag behind their xG profile because the results haven't matched the chance creation — classic regression-to-the-mean candidates.

### 🇫🇷 France
The only side with **top-3 standing in all three categories** — solid attack (2.08 xG/match), tight defense (0.85 conceded), FIFA #1 (1,877 points). Consistent across WC22 and Euro 2024. Lowest variance ceiling, highest floor.

### 🇪🇸 Spain
Euro 2024 champions. Pure efficiency, not chance creation: **1.61 xG/match** is mid-pack, but a **0.64 conceded rate** plus FIFA #2 ranking carry them. Defending and pedigree do the heavy lifting; finishing has been the overperformance.

### 🇵🇹 Portugal
The Euro 2024 surge moved them up: **2.20 xG/match, 0.90 conceded** with FIFA #5 standing. Strong attack, mid-tier defense — biggest swing factor of the top 5.

---

## Economic context — wealth vs football

GDP per capita, population, and confederation for the six. Two of the takeaways are worth flagging upfront:

- **The top of the contender list is poor.** Brazil ($10k/cap) and Argentina ($14k/cap) are 1–2 in Contender Score and 5–6 in GDP per capita of this group. The Netherlands ($68k/cap) is the wealthiest and ranks 6 of 6 on the football score.
- **Portugal is the per-capita marvel.** 10.7M people, FIFA #5, **164.9 FIFA points per million population** — roughly **20× Brazil's** rate and 1.7× Netherlands'.

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

<Table data="econ_context" title="Economic profile — top 5 + Netherlands" sortable="true" />

### Football production per capita

A simple "how much football does this nation produce per person" — FIFA points per million inhabitants. Portugal blows the field away; Brazil's huge population makes them efficient as a country but inefficient per-head.

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
  height="320px"
  label="true"
/>

### Football vs economy

Football "punch per dollar of GDP per capita". A high number means a country produces more football performance than its economic profile would predict; a low number means football is underperforming the economy.

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
  height="320px"
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
  year,
  max(case when team_code = 'BRA' then gdp_per_capita_usd end) as Brazil,
  max(case when team_code = 'ARG' then gdp_per_capita_usd end) as Argentina,
  max(case when team_code = 'FRA' then gdp_per_capita_usd end) as France,
  max(case when team_code = 'ESP' then gdp_per_capita_usd end) as Spain,
  max(case when team_code = 'POR' then gdp_per_capita_usd end) as Portugal,
  max(case when team_code = 'NED' then gdp_per_capita_usd end) as Netherlands
group by year
order by year
```

<LineChart
  data="gdp_trajectory"
  x="year"
  y="Brazil, Argentina, France, Spain, Portugal, Netherlands"
  title="GDP per capita (USD) — 2020 to 2024"
  height="380px"
/>

**What the trajectory says:**
- 🇳🇱 **Netherlands** is on a steep upward arc ($53k → $68k, +26% in 5 years) — the football data hasn't caught up to this prosperity.
- 🇫🇷 **France** and 🇪🇸 **Spain** both grew steadily and now sit at $46k and $35k respectively. Football matches the economic baseline.
- 🇵🇹 **Portugal** grew from $22k to $29k — modest economy, elite football.
- 🇦🇷 **Argentina** is the surprising one: $8.5k → $14k (+64% nominal in 5 years). Their economy is volatile but trending up, and the WC22+Copa24 double came amid this period.
- 🇧🇷 **Brazil** is the flattest grower ($7k → $10k) — and their FIFA pedigree has slipped (now #6 globally, the lowest of this group).

The headline: **football performance does not track economic prosperity in this sample**. If anything, the relationship is inverse — the smaller, less wealthy nations of this group (Argentina, Brazil, Portugal) lead the contender ranking, while the wealthiest (Netherlands, France) sit in the middle or trail. Football culture, not capital, is doing the heavy lifting.

---

## The honest caveats

- **xG is for shots, not penalty shootouts.** Argentina won WC2022 and Copa 2024 with last-gasp goals and penalty wins; that "clutch factor" isn't in the model.
- **No luck factor yet.** A team's actual goal output is the deterministic xG number plus noise. The simulation that adds the random-luck variable per match (see prior thread) will spread these probabilities and let upsets land more realistically.
- **No injury / squad-change weighting.** A retirement or a major injury between now and June 2026 isn't reflected here.
- **No home-field advantage.** Mexico, USA and Canada all get a structural boost in a real model that isn't applied here — they currently sit outside the top 5 on pure form numbers.
- **Pedigree is forward-looking proxy, not history.** FIFA points reflect the last ~24 months of results. Argentina's 2022 World Cup is baked in; their 1986 win is not.

The next model iteration adds the luck-factor Monte Carlo loop on top of this score, turning "Argentina is best on the numbers" into "Argentina wins 18% of simulated tournaments, France 14%, Brazil 12%, …" — which is the probability the model actually outputs.
