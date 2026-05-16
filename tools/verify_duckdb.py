#!/usr/bin/env python3
"""
Sanity-check the built DuckDB database.

Runs a list of named assertions against `data/wc2026.duckdb`. Each
assertion produces `[PASS]` or `[FAIL]` (or `[WARN]` for non-fatal
checks). Exit code is the number of FAILs.

Use after `tools/build_duckdb.py` to confirm the DB is healthy, or as a
CI gate before declaring a build successful.

Usage:
    python3 tools/verify_duckdb.py
    python3 tools/verify_duckdb.py --db-path data/wc2026.duckdb
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "wc2026.duckdb"


@dataclass
class Assertion:
    name: str
    sql: str
    predicate: Callable[[Any], bool]
    severity: str = "FAIL"  # "FAIL" or "WARN"
    explain: str = ""


# Bounds tuned to current data (2026-05-13). When new sources land or
# squad rosters change, ranges may need widening — the actual value is
# always logged so a [FAIL] message is informative.
ASSERTIONS: list[Assertion] = [
    # --- Schema presence ---
    Assertion("schema:raw exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='raw'", lambda n: n == 1),
    Assertion("schema:curated exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='curated'", lambda n: n == 1),
    Assertion("schema:staging exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='staging'", lambda n: n == 1),
    Assertion("schema:quarantine exists", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='quarantine'", lambda n: n == 1),

    # --- Dim row count ranges ---
    Assertion("dim_player row count in [1100, 1500]", "SELECT COUNT(*) FROM curated.dim_player", lambda n: 1100 <= n <= 1500),
    Assertion("dim_team row count in [60, 250]", "SELECT COUNT(*) FROM curated.dim_team", lambda n: 60 <= n <= 250),
    Assertion("dim_tournament row count in [3, 20]", "SELECT COUNT(*) FROM curated.dim_tournament", lambda n: 3 <= n <= 20),
    Assertion("dim_model row count > 0", "SELECT COUNT(*) FROM curated.dim_model", lambda n: n > 0),

    # --- PK no-NULL ---
    Assertion("dim_player.player_id is non-null for every row", "SELECT COUNT(*) FROM curated.dim_player WHERE player_id IS NULL OR player_id = ''", lambda n: n == 0),
    Assertion("dim_team.team_code is non-null for every row", "SELECT COUNT(*) FROM curated.dim_team WHERE team_code IS NULL OR team_code = ''", lambda n: n == 0),
    Assertion("dim_tournament.tournament_id is non-null for every row", "SELECT COUNT(*) FROM curated.dim_tournament WHERE tournament_id IS NULL", lambda n: n == 0),

    # --- PK uniqueness ---
    Assertion(
        "dim_player.player_id is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT player_id) FROM curated.dim_player",
        lambda n: n == 0,
    ),
    Assertion(
        "dim_team.team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.dim_team",
        lambda n: n == 0,
    ),

    # --- player_id format hygiene ---
    Assertion(
        "every dim_player.player_id matches P###### format",
        "SELECT COUNT(*) FROM curated.dim_player WHERE NOT regexp_matches(player_id, '^P[0-9]{6}$')",
        lambda n: n == 0,
    ),

    # --- Registry hygiene: no duplicate (normalized_name, country_code, birth_year) on active players ---
    Assertion(
        "no duplicate (normalized_name, country_code, birth_year) among active players",
        "SELECT COUNT(*) FROM (SELECT normalized_name, country_code, birth_year, COUNT(*) AS n "
        "FROM curated.dim_player WHERE is_active GROUP BY 1, 2, 3 HAVING n > 1)",
        lambda n: n == 0,
        explain="If > 0, the master has accumulated duplicate rows — review db/masters/players.csv",
    ),

    # --- FK integrity ---
    Assertion(
        "every fact_player_xg.player_id exists in dim_player",
        "SELECT COUNT(*) FROM curated.fact_player_xg f "
        "LEFT JOIN curated.dim_player p USING (player_id) WHERE p.player_id IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every non-null fact_player_xg.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_player_xg f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE f.team_code IS NOT NULL AND t.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_team_rating.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_team_rating f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE t.team_code IS NULL",
        lambda n: n == 0,
    ),

    # --- Source coverage (raw tables non-empty) ---
    Assertion("raw.squad_xg_ratings non-empty", "SELECT COUNT(*) FROM raw.squad_xg_ratings", lambda n: n > 0),
    Assertion("raw.sb_player_summary non-empty", "SELECT COUNT(*) FROM raw.sb_player_summary", lambda n: n > 0),
    Assertion("raw.understat_player_xg non-empty", "SELECT COUNT(*) FROM raw.understat_player_xg", lambda n: n > 0),
    Assertion("raw.team_ratings_all_models non-empty", "SELECT COUNT(*) FROM raw.team_ratings_all_models", lambda n: n > 0),

    # --- Match rate floors (drift sentinels) ---
    Assertion(
        "sb_player_summary match rate ≥ 90%",
        "SELECT 100.0 * (SELECT COUNT(*) FROM staging.matched_sb_player_summary) / "
        "(SELECT COUNT(*) FROM raw.sb_player_summary)",
        lambda n: n >= 90.0,
        severity="WARN",
        explain="A canonical squad source should hit ≥ 90%; lower suggests dim_player drift",
    ),

    # --- Quarantine surface (informational) ---
    Assertion(
        "quarantine.unmatched_understat_player_xg <= 7000 rows",
        "SELECT COUNT(*) FROM quarantine.unmatched_understat_player_xg",
        lambda n: n <= 7000,
        severity="WARN",
        explain="Understat universe is large; high quarantine count is expected, not pathological",
    ),

    # --- Facts non-empty ---
    Assertion("fact_player_xg non-empty", "SELECT COUNT(*) FROM curated.fact_player_xg", lambda n: n > 0),
    Assertion("fact_team_rating non-empty", "SELECT COUNT(*) FROM curated.fact_team_rating", lambda n: n > 0),

    # --- Spot-check: at least one player has multi-source coverage ---
    Assertion(
        "at least 50 players have both StatsBomb and Understat xG rows",
        "SELECT COUNT(*) FROM (SELECT player_id FROM curated.fact_player_xg "
        "GROUP BY player_id HAVING COUNT(DISTINCT source) >= 2)",
        lambda n: n >= 50,
    ),

    # === Country-context features (plan 2026-05-14-002) ============================
    # Facts non-empty
    Assertion(
        "fact_team_economics non-empty",
        "SELECT COUNT(*) FROM curated.fact_team_economics",
        lambda n: n > 0,
    ),
    Assertion(
        "fact_team_fifa_ranking non-empty",
        "SELECT COUNT(*) FROM curated.fact_team_fifa_ranking",
        lambda n: n > 0,
    ),
    # View row-count parity with dim_team
    Assertion(
        "dim_team_current row count equals dim_team row count",
        "SELECT (SELECT COUNT(*) FROM curated.dim_team_current) - (SELECT COUNT(*) FROM curated.dim_team)",
        lambda n: n == 0,
    ),

    # --- R10: uniqueness of primary-key columns ---
    Assertion(
        "fact_team_economics (team_code, year) is unique",
        "SELECT COUNT(*) FROM (SELECT team_code, year, COUNT(*) AS n FROM curated.fact_team_economics GROUP BY 1, 2 HAVING n > 1)",
        lambda n: n == 0,
    ),
    Assertion(
        "fact_team_fifa_ranking team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.fact_team_fifa_ranking",
        lambda n: n == 0,
    ),
    Assertion(
        "dim_team_current team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.dim_team_current",
        lambda n: n == 0,
    ),

    # --- FK integrity (R3): country facts join cleanly to dim_team ---
    Assertion(
        "every fact_team_economics.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_team_economics f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE t.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_team_fifa_ranking.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_team_fifa_ranking f "
        "LEFT JOIN curated.dim_team t USING (team_code) WHERE t.team_code IS NULL",
        lambda n: n == 0,
    ),

    # --- R11: last-5-years coverage for every WC2026 qualifier ---
    # Window is computed from the data: [MAX(year) - 4 .. MAX(year)] using rows
    # with at least one non-null measure (the "reported window"). Scotland (SCO)
    # is exempt for the non-null filter because it has no World Bank entity;
    # row-presence is still enforced for SCO via FK + the parquet null-block.
    Assertion(
        "every WC2026 qualifier (except SCO) has GDP for each of the last 5 reported years",
        """
        WITH reported AS (
            SELECT year FROM curated.fact_team_economics
            WHERE gdp_per_capita_usd IS NOT NULL
        ),
        report_window AS (
            SELECT year FROM reported
            WHERE year >= (SELECT MAX(year) FROM reported) - 4
            GROUP BY year
        ),
        qualifiers AS (
            SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier AND team_code <> 'SCO'
        ),
        expected AS (
            SELECT q.team_code, w.year FROM qualifiers q CROSS JOIN report_window w
        )
        SELECT COUNT(*) FROM expected e
        LEFT JOIN curated.fact_team_economics f
          ON f.team_code = e.team_code AND f.year = e.year AND f.gdp_per_capita_usd IS NOT NULL
        WHERE f.team_code IS NULL
        """,
        lambda n: n == 0,
        explain="Missing (team_code, year) cells in the last-5-year window",
    ),
    Assertion(
        "every WC2026 qualifier (except SCO) has population for each of the last 5 reported years",
        """
        WITH reported AS (
            SELECT year FROM curated.fact_team_economics
            WHERE population IS NOT NULL
        ),
        report_window AS (
            SELECT year FROM reported
            WHERE year >= (SELECT MAX(year) FROM reported) - 4
            GROUP BY year
        ),
        qualifiers AS (
            SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier AND team_code <> 'SCO'
        ),
        expected AS (
            SELECT q.team_code, w.year FROM qualifiers q CROSS JOIN report_window w
        )
        SELECT COUNT(*) FROM expected e
        LEFT JOIN curated.fact_team_economics f
          ON f.team_code = e.team_code AND f.year = e.year AND f.population IS NOT NULL
        WHERE f.team_code IS NULL
        """,
        lambda n: n == 0,
    ),

    # --- View coverage: every WC2026 qualifier has FIFA + GDP in the denormalized view ---
    Assertion(
        "every WC2026 qualifier in dim_team_current has fifa_points populated",
        "SELECT COUNT(*) FROM curated.dim_team_current "
        "WHERE is_wc2026_qualifier AND fifa_points IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every WC2026 qualifier (except SCO) in dim_team_current has gdp_per_capita_usd_latest populated",
        "SELECT COUNT(*) FROM curated.dim_team_current "
        "WHERE is_wc2026_qualifier AND team_code <> 'SCO' AND gdp_per_capita_usd_latest IS NULL",
        lambda n: n == 0,
    ),

    # --- Quarantine surface for new facts (informational; zero is the happy path) ---
    Assertion(
        "quarantine.unmatched_team_economics is empty for WC2026 qualifiers",
        "SELECT COUNT(*) FROM quarantine.unmatched_team_economics q "
        "JOIN curated.dim_team t ON t.team_code = q.team_code "
        "WHERE t.is_wc2026_qualifier",
        lambda n: n == 0,
    ),
    Assertion(
        "quarantine.unmatched_team_fifa_ranking is empty for WC2026 qualifiers",
        "SELECT COUNT(*) FROM quarantine.unmatched_team_fifa_ranking q "
        "JOIN curated.dim_team t ON t.team_code = q.team_code "
        "WHERE t.is_wc2026_qualifier",
        lambda n: n == 0,
    ),

    # === International matches (plan 2026-05-15-001) =================================
    Assertion(
        "fact_international_match non-empty",
        "SELECT COUNT(*) FROM curated.fact_international_match",
        lambda n: n > 20000,
    ),
    Assertion(
        "fact_international_match has exactly 4 tournament tiers",
        "SELECT COUNT(DISTINCT tournament_tier) FROM curated.fact_international_match",
        lambda n: n == 4,
    ),
    Assertion(
        "fact_international_match excludes future fixtures",
        "SELECT COUNT(*) FROM curated.fact_international_match "
        "WHERE home_score IS NULL OR away_score IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_international_match.home_team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_international_match f "
        "LEFT JOIN curated.dim_team t ON t.team_code = f.home_team_code "
        "WHERE t.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_international_match.away_team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_international_match f "
        "LEFT JOIN curated.dim_team t ON t.team_code = f.away_team_code "
        "WHERE t.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "fact_international_match (match_date, home_team_code, away_team_code) is unique",
        "SELECT COUNT(*) FROM (SELECT match_date, home_team_code, away_team_code, COUNT(*) AS n "
        "FROM curated.fact_international_match GROUP BY 1, 2, 3 HAVING n > 1)",
        lambda n: n == 0,
    ),
    Assertion(
        "staging.team_match row count is 2 * fact_international_match row count",
        "SELECT (SELECT COUNT(*) FROM staging.team_match) - "
        "       (2 * (SELECT COUNT(*) FROM curated.fact_international_match))",
        lambda n: n == 0,
    ),
    Assertion(
        # Natural key is (team_code, match_date, opponent_team_code, venue). venue
        # disambiguates legitimate same-day double-headers where the same two teams
        # played twice on one day -- one match at each team's home venue
        # (e.g., ARG vs URU on 1916-08-15: Copa Newton in Avellaneda + Copa Lipton
        # in Montevideo). Without venue, those collapse to apparent duplicates.
        "staging.team_match (team_code, match_date, opponent_team_code, venue) is unique",
        "SELECT COUNT(*) FROM (SELECT team_code, match_date, opponent_team_code, venue, COUNT(*) AS n "
        "FROM staging.team_match GROUP BY 1, 2, 3, 4 HAVING n > 1)",
        lambda n: n == 0,
    ),
    Assertion(
        "dim_team_recent_form row count equals dim_team row count",
        "SELECT (SELECT COUNT(*) FROM curated.dim_team_recent_form) - "
        "       (SELECT COUNT(*) FROM curated.dim_team)",
        lambda n: n == 0,
    ),
    Assertion(
        "dim_team_recent_form team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.dim_team_recent_form",
        lambda n: n == 0,
    ),
    Assertion(
        "every WC2026 qualifier in dim_team_recent_form has matches_last_10 >= 5",
        "SELECT COUNT(*) FROM curated.dim_team_recent_form r "
        "JOIN curated.dim_team d USING (team_code) "
        "WHERE d.is_wc2026_qualifier AND (r.matches_last_10 IS NULL OR r.matches_last_10 < 5)",
        lambda n: n == 0,
        explain="R11 floor; a qualifier with <5 resolved matches is a data-quality red flag",
    ),
    Assertion(
        "every WC2026 qualifier in dim_team_recent_form has last_match_date populated",
        "SELECT COUNT(*) FROM curated.dim_team_recent_form r "
        "JOIN curated.dim_team d USING (team_code) "
        "WHERE d.is_wc2026_qualifier AND r.last_match_date IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "quarantine.unmatched_international_matches has no qualifier-vs-qualifier rows",
        "SELECT COUNT(*) FROM quarantine.unmatched_international_matches q "
        "WHERE q.home_team_code IN (SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier) "
        "  AND q.away_team_code IN (SELECT team_code FROM curated.dim_team WHERE is_wc2026_qualifier)",
        lambda n: n == 0,
        explain="If a match between two qualifiers ends up here, dim_team is missing a row",
    ),
    Assertion(
        "quarantine.unmatched_international_matches row count <= 35000",
        "SELECT COUNT(*) FROM quarantine.unmatched_international_matches",
        lambda n: n <= 35000,
        severity="WARN",
        explain="Large quarantine is expected: ~half of martj42's 154-yr history involves teams outside dim_team",
    ),

    # === Tournament tier weights master (plan 2026-05-15-002 refactor) ================
    # The single source of truth for per-tier match-importance weights. Any model
    # that needs these JOINs curated.dim_tournament_tier_weight; do not hardcode.
    Assertion(
        "dim_tournament_tier_weight has exactly 4 rows (one per tier)",
        "SELECT COUNT(*) FROM curated.dim_tournament_tier_weight",
        lambda n: n == 4,
    ),
    Assertion(
        "dim_tournament_tier_weight covers every tier present in fact_international_match",
        "SELECT COUNT(*) FROM ("
        "  SELECT DISTINCT tournament_tier FROM curated.fact_international_match"
        "  EXCEPT"
        "  SELECT tournament_tier FROM curated.dim_tournament_tier_weight"
        ")",
        lambda n: n == 0,
        explain="If a tier exists in fact_international_match but not in the master, weighted queries would silently drop those matches",
    ),
    Assertion(
        "dim_tournament_tier_weight weights are all in (0, 1]",
        "SELECT COUNT(*) FROM curated.dim_tournament_tier_weight WHERE weight <= 0 OR weight > 1",
        lambda n: n == 0,
    ),

    # === Curated-poisson-luck model inputs (plan 2026-05-15-002) =====================
    # These assertions guard the goal-stats query at
    # methodology/curated-poisson-luck/queries/team_goal_stats.sql.
    # Tier weights come from dim_tournament_tier_weight (the master). No literals here.
    Assertion(
        "team_goal_stats: every WC2026 qualifier has a stats row with match_count >= 5",
        """
        WITH team_match AS (
            SELECT home_team_code AS team_code, home_score AS goals_for, away_score AS goals_against, tournament_tier
            FROM curated.fact_international_match WHERE match_date >= DATE '2022-01-01'
            UNION ALL
            SELECT away_team_code, away_score, home_score, tournament_tier
            FROM curated.fact_international_match WHERE match_date >= DATE '2022-01-01'
        ),
        goal_stats AS (
            SELECT team_code, COUNT(*) AS match_count FROM team_match GROUP BY team_code
        )
        SELECT COUNT(*) FROM curated.dim_team team
        LEFT JOIN goal_stats USING (team_code)
        WHERE team.is_wc2026_qualifier
          AND (goal_stats.match_count IS NULL OR goal_stats.match_count < 5)
        """,
        lambda n: n == 0,
        explain="Curated-poisson-luck Unit 1: qualifier must have >=5 matches since 2022 for usable σ_team",
    ),
    Assertion(
        "team_goal_stats: all WC2026 qualifiers produce non-null goals_for_mean and goals_for_std > 0",
        """
        WITH team_match AS (
            SELECT home_team_code AS team_code, home_score AS goals_for, away_score AS goals_against, tournament_tier
            FROM curated.fact_international_match WHERE match_date >= DATE '2022-01-01'
            UNION ALL
            SELECT away_team_code, away_score, home_score, tournament_tier
            FROM curated.fact_international_match WHERE match_date >= DATE '2022-01-01'
        ),
        weighted AS (
            SELECT team_match.team_code, team_match.goals_for, team_match.goals_against, tier_weight.weight
            FROM team_match
            JOIN curated.dim_tournament_tier_weight tier_weight USING (tournament_tier)
        ),
        means AS (
            SELECT team_code, SUM(weight) AS weight_sum, SUM(weight * goals_for) / SUM(weight) AS goals_for_mean
            FROM weighted GROUP BY team_code
        ),
        goal_stats AS (
            SELECT weighted.team_code, means.goals_for_mean,
                SQRT(SUM(weighted.weight * (weighted.goals_for - means.goals_for_mean) * (weighted.goals_for - means.goals_for_mean)) / means.weight_sum) AS goals_for_std
            FROM weighted JOIN means USING (team_code)
            GROUP BY weighted.team_code, means.goals_for_mean, means.weight_sum
        )
        SELECT COUNT(*) FROM curated.dim_team team
        LEFT JOIN goal_stats USING (team_code)
        WHERE team.is_wc2026_qualifier
          AND (goal_stats.goals_for_mean IS NULL OR goal_stats.goals_for_std IS NULL OR goal_stats.goals_for_std <= 0)
        """,
        lambda n: n == 0,
        explain="Curated-poisson-luck Unit 1: degenerate stats break the luck-factor truncated-Normal draw",
    ),

    # === Squad-pool xG facts =======================================================
    Assertion(
        "fact_player_xg_per_90 row count in [1200, 1300]",
        "SELECT COUNT(*) FROM curated.fact_player_xg_per_90",
        lambda n: 1200 <= n <= 1300,
    ),
    Assertion(
        "fact_player_xg_per_90.player_id is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT player_id) FROM curated.fact_player_xg_per_90",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_player_xg_per_90.player_id exists in dim_player",
        "SELECT COUNT(*) FROM curated.fact_player_xg_per_90 player_xg "
        "LEFT JOIN curated.dim_player USING (player_id) WHERE dim_player.player_id IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_player_xg_per_90.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_player_xg_per_90 player_xg "
        "LEFT JOIN curated.dim_team USING (team_code) WHERE dim_team.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "fact_team_xg has at least 40 rows",
        "SELECT COUNT(*) FROM curated.fact_team_xg",
        lambda n: n >= 40,
    ),
    Assertion(
        "fact_team_xg.team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.fact_team_xg",
        lambda n: n == 0,
    ),
    Assertion(
        "every WC2026 qualifier with squad data has top_11_blended_xg_per_90 populated",
        "SELECT COUNT(*) FROM curated.dim_team team "
        "LEFT JOIN curated.fact_team_xg team_xg USING (team_code) "
        "WHERE team.is_wc2026_qualifier AND team_xg.team_code IS NOT NULL "
        "  AND (team_xg.top_11_blended_xg_per_90 IS NULL OR team_xg.players_in_pool < 11)",
        lambda n: n == 0,
        explain="If > 0, some qualifier has fewer than 11 players in the squad pool — squad_xg_ratings may be stale",
    ),
    Assertion(
        "fact_team_xg.top_11_blended_xg_per_90 in plausible range [0.3, 4.0] for qualifiers",
        "SELECT COUNT(*) FROM curated.fact_team_xg "
        "WHERE is_wc2026_qualifier "
        "  AND (top_11_blended_xg_per_90 < 0.3 OR top_11_blended_xg_per_90 > 4.0)",
        lambda n: n == 0,
        explain="Top-11 xG aggregate outside [0.3, 4.0] suggests a data issue (rare for a single match)",
    ),

    # === Defensive xG facts ========================================================
    Assertion(
        "fact_team_xg_against has one row per dim_team",
        "SELECT (SELECT COUNT(*) FROM curated.fact_team_xg_against) "
        "     - (SELECT COUNT(*) FROM curated.dim_team)",
        lambda n: n == 0,
    ),
    Assertion(
        "fact_team_xg_against.team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.fact_team_xg_against",
        lambda n: n == 0,
    ),
    Assertion(
        "at least 30 teams have a non-null blended_xga_per_90",
        "SELECT COUNT(*) FROM curated.fact_team_xg_against WHERE blended_xga_per_90 IS NOT NULL",
        lambda n: n >= 30,
    ),
    Assertion(
        "fact_team_xg_against.blended_xga_per_90 in plausible range [0.3, 3.5] when populated",
        "SELECT COUNT(*) FROM curated.fact_team_xg_against "
        "WHERE blended_xga_per_90 IS NOT NULL "
        "  AND (blended_xga_per_90 < 0.3 OR blended_xga_per_90 > 3.5)",
        lambda n: n == 0,
        explain="An xGA aggregate outside [0.3, 3.5] suggests upstream data corruption",
    ),
    Assertion(
        "fact_team_xg_against_wc2022 has 32 rows (WC2022 teams)",
        "SELECT COUNT(*) FROM curated.fact_team_xg_against_wc2022",
        lambda n: n == 32,
    ),
    Assertion(
        "fact_team_xg_against_wc2022.team_code is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT team_code) FROM curated.fact_team_xg_against_wc2022",
        lambda n: n == 0,
    ),
    Assertion(
        "every fact_team_xg_against_wc2022.team_code exists in dim_team",
        "SELECT COUNT(*) FROM curated.fact_team_xg_against_wc2022 wc "
        "LEFT JOIN curated.dim_team USING (team_code) WHERE dim_team.team_code IS NULL",
        lambda n: n == 0,
    ),
    Assertion(
        "fact_team_xg_against_wc2022: at least 30 teams have pre_wc2022_blended_xga_per_90 populated",
        "SELECT COUNT(*) FROM curated.fact_team_xg_against_wc2022 WHERE pre_wc2022_blended_xga_per_90 IS NOT NULL",
        lambda n: n >= 30,
    ),
]


def run_assertion(con: duckdb.DuckDBPyConnection, a: Assertion) -> tuple[str, Any]:
    try:
        result = con.sql(a.sql).fetchone()
        val = result[0] if result else None
        ok = a.predicate(val)
        if ok:
            return "PASS", val
        return a.severity, val
    except Exception as e:
        return "ERROR", str(e)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}. Run tools/build_duckdb.py first.", file=sys.stderr)
        return 1

    con = duckdb.connect(str(args.db_path), read_only=True)
    fail_count = 0
    warn_count = 0
    pass_count = 0

    print(f"Verifying {args.db_path.relative_to(ROOT) if args.db_path.is_relative_to(ROOT) else args.db_path}\n")
    for a in ASSERTIONS:
        status, val = run_assertion(con, a)
        prefix = f"[{status:<5}]"
        if status == "PASS":
            print(f"  {prefix} {a.name}  =>  {val}")
            pass_count += 1
        elif status == "WARN":
            print(f"  {prefix} {a.name}  =>  {val}  {('— ' + a.explain) if a.explain else ''}")
            warn_count += 1
        elif status == "FAIL":
            print(f"  {prefix} {a.name}  =>  {val}  {('— ' + a.explain) if a.explain else ''}")
            fail_count += 1
        else:  # ERROR
            print(f"  {prefix} {a.name}  =>  {val}")
            fail_count += 1

    con.close()

    print(f"\nSummary: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")
    return fail_count


if __name__ == "__main__":
    sys.exit(main())
