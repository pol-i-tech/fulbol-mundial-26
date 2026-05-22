#!/usr/bin/env python3
"""
Pull WC2026 squad lists from ESPN's single-page squad article.

Source: https://www.espn.com/soccer/story/_/id/48757621/2026-world-cup-squad-lists-players-announced-all-48-teams
Cadence: daily 2026-05-22 → 2026-05-29 (FIFA squad deadline), then on-demand.

The article is the cleanest single-page WC2026 roster source: per-team H4
headings, four bolded position subheadings (Goalkeepers / Defenders /
Midfielders / Forwards), one player per link with a stable ESPN player ID
in the URL path, and a club in parentheses.

Saves:
  data/raw/squads/espn/<YYYY-MM-DD>/page.html         (cached HTML; reused same day)
  data/raw/squads/espn/<YYYY-MM-DD>/wc2026_squads.json (parsed roster snapshot)

Output JSON schema:
{
  "as_of_date": "YYYY-MM-DD",
  "source_url": "...",
  "teams": [
    {
      "nation": "Mexico",
      "group": "GROUP A",
      "announced_date": "May 18",       # nullable
      "manager": "Javier Aguirre",      # nullable
      "players": [
        {"espn_player_id": "236368",
         "name": "Carlos Acevedo",
         "position_bucket": "GK",
         "club": "Santos Laguna"}
      ]
    }
  ]
}

Idempotent: re-running on the same day reuses the cached HTML and produces
byte-identical JSON.

Usage:
  python3 tools/pull_espn_wc2026_squads.py
  python3 tools/pull_espn_wc2026_squads.py --date 2026-05-22  # force a specific dated dir
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = ROOT / "data" / "raw" / "squads" / "espn"


def _rel(p: Path) -> str:
    """Repo-relative path when inside ROOT, absolute otherwise. Cosmetic for logs."""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)

URL = (
    "https://www.espn.com/soccer/story/_/id/48757621/"
    "2026-world-cup-squad-lists-players-announced-all-48-teams"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WC2026-research/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

POSITION_BUCKETS = {
    "goalkeepers": "GK",
    "defenders": "DF",
    "midfielders": "MF",
    "forwards": "FW",
}

NOT_YET_ANNOUNCED = "roster yet to be announced"

# ESPN player-profile URL embeds the player ID:
#   .../soccer/player/_/id/236368/carlos-acevedo
# Club/team URLs use /soccer/team/_/id/...; we deliberately exclude those.
ESPN_ID_RE = re.compile(r"/soccer/player/_/id/(\d+)", re.IGNORECASE)


def fetch_html(out_dir: Path) -> str:
    """Fetch the article HTML, caching it under out_dir/page.html.

    Reuses the cache when present so re-runs on the same day issue zero
    HTTP requests.
    """
    cache = out_dir / "page.html"
    if cache.exists():
        print(f"[cache] {_rel(cache)}")
        return cache.read_text(encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    cache.write_text(html, encoding="utf-8")
    print(f"[fetched] {len(html):,} bytes → {_rel(cache)}")
    return html


def _text(tag: Tag) -> str:
    return tag.get_text(" ", strip=True)


def _is_group_heading(tag: Tag) -> bool:
    if tag.name not in ("h2", "h3", "h4"):
        return False
    txt = _text(tag).upper()
    return bool(re.match(r"^GROUP [A-L]\b", txt))


def _is_team_heading(tag: Tag) -> bool:
    if tag.name not in ("h2", "h3", "h4"):
        return False
    txt = _text(tag)
    if not txt or _is_group_heading(tag):
        return False
    if len(txt) > 80:
        return False
    if txt.lower().startswith("group "):
        return False
    return True


def _position_bucket(tag: Tag) -> Optional[str]:
    """Return GK/DF/MF/FW if this tag introduces a position section."""
    txt = _text(tag).rstrip(":").strip().lower()
    return POSITION_BUCKETS.get(txt)


def _strip_position_label(text: str) -> str:
    """Remove a leading 'Goalkeepers:' / 'Defenders:' / etc. label."""
    return re.sub(
        r"^\s*(?:Goalkeepers|Defenders|Midfielders|Forwards)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )


def _build_player_id_map(node: Tag) -> dict[str, str]:
    """Map anchor text → ESPN player ID for every player anchor in the node.

    ESPN only anchors a subset of players (those with profile pages). Plain-text
    names are common; we still want to capture them with espn_player_id = None.
    """
    out: dict[str, str] = {}
    for a in node.find_all("a", href=True):
        href = a.get("href") or ""
        m = ESPN_ID_RE.search(href)
        if not m:
            continue
        name = a.get_text(" ", strip=True)
        if name:
            out.setdefault(name, m.group(1))
    return out


def _parse_player_list(text: str, name_to_id: dict[str, str], bucket: str) -> list[dict]:
    """Parse a 'Name (Club), Name (Club), ...' string into player dicts.

    Splits on commas that occur OUTSIDE parentheses so club names containing
    commas are tolerated. ESPN IDs are filled in from the anchor map when the
    name matches; otherwise espn_player_id is None.
    """
    # ESPN position lists are flat — clubs never legitimately nest parens.
    # When an opening paren appears while depth=1 (e.g., a missing close paren
    # upstream like "Hakan Calhanoglou (Inter Milan, Kaan Ayhan (Galatasaray)..."),
    # treat it as a recovery point: close the prior paren and restart.
    players: list[dict] = []
    depth = 0
    buf: list[str] = []
    pieces: list[str] = []
    for ch in text:
        if ch == "(":
            if depth >= 1:
                # Recover: emit a synthetic close, force depth back to 0.
                buf.append(")")
                depth = 0
                # Treat as boundary: push current buf, start new piece with this '('
                pieces.append("".join(buf).strip())
                buf = []
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            pieces.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        pieces.append("".join(buf).strip())

    for piece in pieces:
        # ESPN occasionally ends the last item with a period (e.g.,
        # "Francisco Trincão (Sporting Lisbon)."); strip terminating punctuation.
        piece = piece.strip(" .;:")
        if not piece:
            continue
        m = re.match(r"^(?P<name>.+?)\s*\((?P<club>[^)]+)\)\s*$", piece)
        if m:
            name = m.group("name").strip()
            club = m.group("club").strip() or None
        else:
            name = piece.strip()
            club = None
        if not name or len(name) < 2:
            continue
        # Strip trailing punctuation/junk from the name
        name = re.sub(r"\s+", " ", name).strip(" .,;:")
        if not name:
            continue
        players.append(
            {
                "espn_player_id": name_to_id.get(name),
                "name": name,
                "position_bucket": bucket,
                "club": club,
            }
        )
    return players


def _walk_player_paragraph(node: Tag, bucket: str) -> list[dict]:
    """Extract players from a position paragraph.

    The paragraph shape is `<strong>Goalkeepers</strong>: Name (Club), Name (Club), ...`
    where SOME names are wrapped in player anchors and others are plain text.
    """
    name_to_id = _build_player_id_map(node)
    text = _strip_position_label(node.get_text(" ", strip=True))
    return _parse_player_list(text, name_to_id, bucket)


def _find_manager_in_text(text: str) -> Optional[str]:
    m = re.search(r"Manager\s*:\s*([^\n\r]+?)(?:\s*$|\.|;|\|)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _find_announced_in_text(text: str) -> tuple[Optional[str], Optional[str]]:
    """Return (announced_date, announce_type).

    announce_type is one of:
      'final'       — final squad / roster announced
      'preliminary' — preliminary or provisional squad/roster announced
      None          — no announcement phrase detected
    """
    # Preliminary or provisional first (ESPN has typos like "toster" for "roster")
    m = re.search(
        r"\b(Preliminary|Provisional)\s+(?:squad|roster|toster)\s+(?:was\s+)?announced"
        r"(?:\s+on)?\s+([A-Z][a-z]+\s+\d{1,2})",
        text,
    )
    if m:
        return m.group(2).strip(), "preliminary"
    # Explicit "Final squad announced ..."
    m = re.search(
        r"\bFinal\s+squad\s+(?:was\s+)?announced(?:\s+on)?\s+([A-Z][a-z]+\s+\d{1,2})",
        text,
    )
    if m:
        return m.group(1).strip(), "final"
    # Plain "Roster announced ..." with no qualifier — treated as final
    m = re.search(
        r"\bRoster\s+(?:was\s+)?announced(?:\s+on)?\s+([A-Z][a-z]+\s+\d{1,2})",
        text,
    )
    if m:
        return m.group(1).strip(), "final"
    return None, None


def _dedup_players(players: list[dict]) -> list[dict]:
    """Dedup within a team. Key on espn_player_id when present, else on name."""
    seen: set[str] = set()
    out: list[dict] = []
    for p in players:
        key = p["espn_player_id"] or f"name:{p['name'].lower()}"
        if key in seen:
            print(
                f"WARN: duplicate player {key} ({p.get('name')}); dropping dup",
                file=sys.stderr,
            )
            continue
        seen.add(key)
        out.append(p)
    return out


def parse_squads(html: str) -> list[dict]:
    """Parse the ESPN article HTML into a list of team dicts."""
    soup = BeautifulSoup(html, "html.parser")

    # The article body lives inside the story container; collect every
    # heading and content node in document order, then walk linearly so we
    # can attach paragraphs to the most recent team + position bucket.
    root = (
        soup.find("div", class_="article-body")
        or soup.find("article")
        or soup
    )

    nodes: list[Tag] = []
    for tag in root.find_all(["h2", "h3", "h4", "h5", "p", "ul", "ol"]):
        nodes.append(tag)

    teams: list[dict] = []
    current_group: Optional[str] = None
    current_team: Optional[dict] = None
    team_text_buffer: list[str] = []

    def flush_team():
        nonlocal current_team, team_text_buffer
        if current_team is None:
            return
        joined = " ".join(team_text_buffer)
        if current_team.get("manager") is None:
            current_team["manager"] = _find_manager_in_text(joined)
        if current_team.get("announced_date") is None:
            date_str, ann_type = _find_announced_in_text(joined)
            current_team["announced_date"] = date_str
            current_team["announce_type"] = ann_type
        current_team["players"] = _dedup_players(current_team["players"])
        # Drop teams whose roster wasn't announced (no players AND sentinel text)
        if not current_team["players"] and NOT_YET_ANNOUNCED in joined.lower():
            pass  # skip not-yet-announced teams entirely
        else:
            teams.append(current_team)
        current_team = None
        team_text_buffer = []

    for node in nodes:
        if _is_group_heading(node):
            flush_team()
            current_group = _text(node).upper()
            continue

        if _is_team_heading(node) and current_group is not None:
            flush_team()
            nation = re.sub(r"\s+", " ", _text(node)).strip()
            current_team = {
                "nation": nation,
                "group": current_group,
                "announced_date": None,
                "announce_type": None,
                "manager": None,
                "players": [],
            }
            continue

        if current_team is None:
            continue

        # Accumulate text for manager/announce extraction
        team_text_buffer.append(_text(node))

        # Position paragraphs only — never continuation. A position paragraph
        # leads with a known label, either as plain text or wrapped in
        # <strong>/<b>. Lines without that lead (announce/manager/sentinel)
        # are ignored for player extraction.
        bucket = _position_bucket(node)
        if bucket is None and isinstance(node, Tag):
            strong = node.find(["strong", "b"])
            if strong is not None:
                bucket = _position_bucket(strong)
        if bucket is not None:
            current_team["players"].extend(_walk_player_paragraph(node, bucket))

    flush_team()
    return teams


def write_output(out_dir: Path, teams: list[dict], today: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of_date": today,
        "source_url": URL,
        "teams": teams,
    }
    path = out_dir / "wc2026_squads.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument(
        "--date",
        default=None,
        help="Override the dated directory (default: today, YYYY-MM-DD)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    today = args.date or str(date.today())
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        print(f"ERROR: --date must be YYYY-MM-DD (got {today!r})", file=sys.stderr)
        return 2
    out_dir = BASE_DIR / today

    try:
        html = fetch_html(out_dir)
    except urllib.error.HTTPError as e:
        print(f"ERROR: HTTP {e.code} fetching ESPN article", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if "<h" not in html.lower():
        print("ERROR: cached HTML has no headings; refusing to write empty JSON", file=sys.stderr)
        return 1

    teams = parse_squads(html)
    if not teams:
        print(
            "ERROR: parser found zero teams; ESPN page structure may have changed",
            file=sys.stderr,
        )
        return 1

    path = write_output(out_dir, teams, today)

    total_players = sum(len(t["players"]) for t in teams)
    print(f"[ok] {len(teams)} teams, {total_players} players → {_rel(path)}")
    if teams:
        sample = teams[0]
        print(
            f"     sample: {sample['nation']} ({sample['group']}) — "
            f"{len(sample['players'])} players"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
