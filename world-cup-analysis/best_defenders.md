---
title: Best Defenders Coming Into WC2026
layout: notebook
---

# Best defenders heading into the 2026 World Cup

Honest framing first: we have **offensive xG / xA** per player from Understat, but **no per-player defensive metrics** (goals-conceded-on-pitch, tackles, interceptions). So "best defender" is approached through three lenses we *can* measure:

1. **Coach trust** — 2025-26 club minutes for established defenders at top clubs
2. **Modern-defender attacking output** — xG + xA per 90 (ball-playing CBs and overlapping fullbacks)
3. **Country depth** — how many regular-starter defenders each WC2026-bound nation can field

Filters used throughout: position contains `'D'`, 2025-26 club season, minimum **1,500 minutes** (≈ half-season starter), player's nation is a WC2026 qualifier.

```sql defenders_base
from graphene_cli.curated.fact_player_xg
where
  source = 'understat'
  and period_id = 'club_2526'
  and dim_player.position like '%D%'
  and minutes >= 1500
  and dim_player.nation.is_wc2026_qualifier
select
  dim_player.player_id as player_id,
  dim_player.display_name as name,
  dim_player.nation.team_name as country,
  dim_player.nation.confederation as confederation,
  dim_player.current_club as club,
  dim_player.current_league as league,
  dim_player.position as position,
  minutes,
  goals,
  xg_total,
  xa_total,
  (xg_total + xa_total) as xg_plus_xa,
  (xg_total + xa_total) / (minutes / 90.0) as xg_xa_per_90
```

```sql totals
from defenders_base
select count(*) as n_defenders, count(distinct country) as n_countries
```

**<Value data=totals column=n_defenders />** WC2026-bound defenders qualify (≥ 1,500 club minutes in 2025-26 Understat coverage), across **<Value data=totals column=n_countries />** countries.

## 1. Most-trusted defenders — by 2025-26 club minutes

These players are the ones their club managers refuse to take off the pitch. A useful proxy for "good enough to start every week at a top-five-league side."

```sql top_by_minutes
from defenders_base
select name, country, club, league, position, minutes, goals
order by minutes desc
limit 20
```

<Table data="top_by_minutes" rowNumbers="true" compact="true">
  <Column id="name" title="Player" />
  <Column id="country" title="Country" />
  <Column id="club" title="Club" />
  <Column id="league" title="League" />
  <Column id="position" title="Pos" align="center" />
  <Column id="minutes" title="Minutes" align="right" />
  <Column id="goals" title="Goals" align="right" />
</Table>

## 2. Defenders who attack — xG + xA per 90

Modern football rewards defenders who initiate or finish attacking moves. This view ranks by per-90 attacking contribution — a fingerprint of overlapping fullbacks (high xA) and aerial-threat centre-backs (high xG from set pieces).

```sql top_by_offense
from defenders_base
where minutes >= 1500
select name, country, club, position, minutes, xg_total, xa_total, xg_xa_per_90
order by xg_xa_per_90 desc
limit 15
```

<BarChart
  title="Top 15 WC2026-bound defenders by xG + xA per 90 (club 2025-26)"
  data="top_by_offense"
  x="name"
  y="xg_xa_per_90"
  sort="xg_xa_per_90 desc"
  label="true"
  height="420px"
/>

<Table data="top_by_offense" compact="true">
  <Column id="name" title="Player" />
  <Column id="country" title="Country" />
  <Column id="club" title="Club" />
  <Column id="position" title="Pos" align="center" />
  <Column id="minutes" title="Min" align="right" />
  <Column id="xg_total" title="xG" align="right" />
  <Column id="xa_total" title="xA" align="right" />
  <Column id="xg_xa_per_90" title="xG+xA / 90" align="right" />
</Table>

## 3. Minutes vs. attacking output

The defenders who anchor *and* attack — top-right is the elite quadrant.

<ScatterPlot
  title="Defender club minutes vs. xG + xA per 90"
  data="defenders_base"
  x="minutes"
  y="xg_xa_per_90"
  splitBy="confederation"
  height="420px"
/>

## 4. Country depth at defense

How many regular-starter defenders does each WC2026-bound nation actually have in top-tier club football?

```sql country_depth
from defenders_base
select country, confederation, count(*) as n_starters
order by n_starters desc
limit 20
```

<BarChart
  title="WC2026 nations by count of regular-starter defenders (≥1,500 club minutes, 2025-26)"
  data="country_depth"
  x="country"
  y="n_starters"
  splitBy="confederation"
  sort="n_starters desc"
  label="true"
  height="380px"
/>

## Caveats

- Understat coverage skews to Europe's top five leagues plus a handful of others. Defenders playing in non-covered leagues (Liga MX, MLS, Eredivisie outside top clubs, Saudi Pro League, etc.) will appear under-represented or absent. Many quality defenders from CONCACAF / CAF / AFC nations are missed by this view alone.
- "Position contains D" includes defensive midfielders coded as `D M S` and attacking fullbacks coded as `D F M S`. The view does not separate centre-backs from fullbacks.
- The dataset is point-in-time (as of the most recent Understat pull). Late-season injuries or rotations are not reflected.
