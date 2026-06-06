"""Read-only narrative-context extractors for the WC2026 report.

Supplies the *color* the report prints — top xG players per team and economic
facts per team. Strictly read-only: never writes to DuckDB (MDM discipline —
facts are read, masters are never extended from them).

These feed prose ONLY. Nothing here enters the prediction engine, so economics
can't bias the model against teams that overperform their GDP.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "data" / "wc2026.duckdb"


@dataclass(frozen=True)
class Player:
    name: str
    position: str
    club: str
    xg90: float | None        # blended xG/90 (national + club)
    national_xg90: float | None


@dataclass(frozen=True)
class TeamEcon:
    team_name: str
    gdp_per_capita_usd: float | None
    population: float | None
    fifa_rank: int | None
    confederation: str | None


def connect(db: Path | str = DB) -> duckdb.DuckDBPyConnection:
    """Open a read-only connection to the analytics DB."""
    return duckdb.connect(str(db), read_only=True)


def top_players(con: duckdb.DuckDBPyConnection, team_code: str, n: int = 3) -> list[Player]:
    """Top-n players for a team by blended xG/90. Returns [] when a team has no
    player rows (data-poor teams degrade gracefully — never raises)."""
    rows = con.execute(
        """
        SELECT d.display_name, f.position, f.current_club,
               f.blended_xg_per_90, f.national_team_xg_per_90
        FROM curated.fact_player_xg_per_90 f
        JOIN curated.dim_player d ON d.player_id = f.player_id
        WHERE f.team_code = ?
        ORDER BY f.blended_xg_per_90 DESC NULLS LAST
        LIMIT ?
        """,
        [team_code, n],
    ).fetchall()
    return [
        Player(
            name=r[0],
            position=(r[1] or "").strip(),
            club=(r[2] or "").strip(),
            xg90=None if r[3] is None else float(r[3]),
            national_xg90=None if r[4] is None else float(r[4]),
        )
        for r in rows
    ]


def team_econ(con: duckdb.DuckDBPyConnection, team_code: str) -> TeamEcon | None:
    """Economic + ranking facts for a team. Returns None if the team isn't in
    the current dim. Falls back to the latest non-null GDP/population year in
    fact_team_economics when the 'latest' snapshot columns are null."""
    row = con.execute(
        """
        SELECT team_name, gdp_per_capita_usd_latest, population_latest,
               fifa_rank, confederation
        FROM curated.dim_team_current
        WHERE team_code = ?
        """,
        [team_code],
    ).fetchone()
    if row is None:
        return None

    team_name, gdp, pop, fifa_rank, conf = row

    if gdp is None or pop is None:
        fb = con.execute(
            """
            SELECT gdp_per_capita_usd, population
            FROM curated.fact_team_economics
            WHERE team_code = ?
              AND gdp_per_capita_usd IS NOT NULL
            ORDER BY year DESC
            LIMIT 1
            """,
            [team_code],
        ).fetchone()
        if fb is not None:
            gdp = gdp if gdp is not None else fb[0]
            pop = pop if pop is not None else fb[1]

    return TeamEcon(
        team_name=team_name,
        gdp_per_capita_usd=None if gdp is None else float(gdp),
        population=None if pop is None else float(pop),
        fifa_rank=None if fifa_rank is None else int(fifa_rank),
        confederation=conf,
    )
