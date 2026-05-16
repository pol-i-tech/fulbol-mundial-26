# db/NAMING.md — SQL naming standard

**Status:** active. **Applies to:** every SQL artifact under `db/sql/`, `db/queries/`, and `methodology/*/queries/`, plus any Python or Markdown that documents or reads the resulting columns.

## Why this exists

A modeler reading `gf_mean` has to look up that `gf` = "goals for". A reader of `sos` has to learn it means strength-of-schedule. A query with `JOIN curated.dim_team t USING (team_code)` forces the reader to scan the FROM block to decode every column reference. The cost is paid every time someone joins this codebase or comes back to it after a month away.

The rule: **complete words for column names, CTE names, table names, and join aliases — with a tightly scoped allowlist of statistical shorts and domain acronyms.**

---

## 1. Column names — complete words

**Allowed statistical shorts (the only English-word abbreviations permitted):**

| Short | Meaning |
|---|---|
| `avg` | average |
| `std` | standard deviation |
| `mean` | mean |
| `stats` | statistics |

**Allowed domain acronyms** (canonical names of the underlying concepts, not abbreviations of English words):

`xg`, `xa`, `fifa`, `gdp`, `iso2`, `iso3`, `usd`, `eur`

Everything else gets the complete word.

| Bad | Good |
|---|---|
| `gf` | `goals_for` |
| `ga` | `goals_against` |
| `gf_mean` | `goals_for_mean` |
| `gf_std` | `goals_for_std` |
| `n_matches` | `match_count` |
| `w_sum` | `weight_sum` |
| `hist_gf_mean` | `historical_goals_for_mean` |
| `goal_diff` | `goal_difference` |
| `pct_won` | `percent_won` |
| `pts` | `points` |
| `cnt` | `count` |

## 2. CTE names — complete words

Same rule as column names: complete English, with the four allowed shorts (`avg`, `std`, `mean`, `stats`).

| Bad | Good |
|---|---|
| `sos` | `strength_of_schedule` |
| `tmp` | (rename to describe what the CTE produces) |
| `agg` | `aggregates` (or, better, name what is being aggregated) |
| `calc` | (rename to describe what is being computed) |
| `t1`, `t2` | (rename to describe the contents) |

`goal_stats` is **fine** — `stats` is on the allowed-shorts list. Same for `match_stats`, `weighted_stats`, etc.

## 3. Table aliases — complete words or no alias

Single-letter and two-letter aliases in `JOIN ... <alias>` and `SELECT <alias>.col` are not allowed.

| Bad | Good |
|---|---|
| `JOIN curated.dim_team t USING (team_code)` | `JOIN curated.dim_team team USING (team_code)` |
| `JOIN curated.dim_team t USING (team_code)` | `JOIN curated.dim_team USING (team_code)` (no alias — often clearest) |
| `FROM team_match tm` | `FROM team_match` |
| `LEFT JOIN dim_tournament_tier_weight tw` | `LEFT JOIN curated.dim_tournament_tier_weight USING (tournament_tier)` |

A CTE that's already complete-named can self-reference without an alias. Aliasing a long table to a single letter is the case the rule is designed to outlaw.

## 4. What this rule does NOT cover

- **Raw-layer columns.** `raw.*` mirrors `data/derived/*.parquet` 1:1 and inherits names from upstream sources (StatsBomb, Understat, World Bank). The rule kicks in at the first transformation (curated or staging).
- **Master-CSV columns** (`db/masters/*.csv`). These travel with the committed data; renaming them is a data migration, not a naming standard. Out of scope.
- **Physical file names** (`team_goal_stats_for_modeling.sql`). File names already use complete words; no rename pass needed.
- **Table-name prefixes** (`dim_*`, `fact_*`, `staging.*`). These are the project's data-modeling convention, not English-word abbreviations. They stay.

## 5. Example — before and after

A real CTE block from `db/queries/examples/team_goal_stats_for_modeling.sql`. The two columns of the change side-by-side:

**Before:**

```sql
WITH
team_match AS (
    SELECT home_team_code AS team_code, home_score AS gf, away_score AS ga, tournament_tier
    FROM curated.fact_international_match
    UNION ALL
    SELECT away_team_code, away_score, home_score, tournament_tier
    FROM curated.fact_international_match
),
weighted AS (
    SELECT tm.team_code, tm.gf, tm.ga, tw.weight AS w
    FROM team_match tm
    JOIN curated.dim_tournament_tier_weight tw USING (tournament_tier)
),
means AS (
    SELECT team_code, COUNT(*) AS n_matches, SUM(w) AS w_sum,
           SUM(w*gf)/SUM(w) AS gf_mean,
           SUM(w*ga)/SUM(w) AS ga_mean
    FROM weighted GROUP BY team_code
)
```

**After:**

```sql
WITH
team_match AS (
    SELECT home_team_code AS team_code, home_score AS goals_for, away_score AS goals_against, tournament_tier
    FROM curated.fact_international_match
    UNION ALL
    SELECT away_team_code, away_score, home_score, tournament_tier
    FROM curated.fact_international_match
),
weighted AS (
    SELECT team_match.team_code, team_match.goals_for, team_match.goals_against, tier_weight.weight
    FROM team_match
    JOIN curated.dim_tournament_tier_weight tier_weight USING (tournament_tier)
),
means AS (
    SELECT team_code, COUNT(*) AS match_count, SUM(weight) AS weight_sum,
           SUM(weight * goals_for) / SUM(weight) AS goals_for_mean,
           SUM(weight * goals_against) / SUM(weight) AS goals_against_mean
    FROM weighted GROUP BY team_code
)
```

## 6. Enforcement

Manual review for now. The PR reviewer checks every new SQL diff against the rules in sections 1–3.

A mechanical linter (`tools/lint_sql_names.py`) that greps for disallowed patterns and exits non-zero is a future follow-up — useful, but not load-bearing while the rule set is small and the active SQL surface is ~15 files.

---

**See also:** [`db/SCHEMA.md`](SCHEMA.md) for the column inventory of every `curated.*` table; this naming standard governs the columns documented there.
