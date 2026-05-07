#!/usr/bin/env python3
"""
Resolve Sofascore player IDs for WC2026 squad players.

Searches Sofascore by player name and validates the result against
known nationality / club. Builds a persistent name → ID mapping.

Input:  data/raw/squads/wc2026_squads_confirmed.json  (or sb fallback)
Output: data/raw/sofascore/player_id_map.json

Usage:
  python3 tools/resolve_sofascore_ids.py
"""
import json, time, unicodedata, urllib.request, urllib.parse
from pathlib import Path

ROOT    = Path(__file__).parent.parent
SQUADS  = ROOT / "data" / "raw" / "squads" / "wc2026_squads_confirmed.json"
SB_SUMM = ROOT / "data" / "derived" / "sb_player_summary.parquet"
OUT     = ROOT / "data" / "raw" / "sofascore" / "player_id_map.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.sofascore.com/",
    "Accept": "application/json, */*",
}

# Nation name → Sofascore country name
NATION_ALIASES = {
    "USA":                    "United States",
    "Czechia":                "Czech Republic",
    "Türkiye":                "Turkey",
    "Ivory Coast":            "Côte d'Ivoire",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "DR Congo":               "DR Congo",
    "South Korea":            "South Korea",
}


def strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def name_variants(name):
    """Generate search query variants from shortest to most specific."""
    parts = name.strip().split()
    variants = [name]  # full name first
    if len(parts) > 2:
        variants.append(f"{parts[0]} {parts[1]}")   # first two words
        variants.append(f"{parts[0]} {parts[-1]}")  # first + last word
    return variants


def score_results(results, name):
    """Score Sofascore search results and return best (pid, name, club) or None."""
    name_simple = strip_accents(name).lower()
    best = None
    best_score = -1

    for r in results[:5]:
        e = r.get("entity", {})
        pid        = e.get("id")
        pname      = e.get("name", "")
        team       = e.get("team", {}) or {}
        club       = team.get("name", "")
        national   = team.get("national", False)
        user_count = e.get("userCount", 0)

        if national:
            continue

        score = 0
        found_simple = strip_accents(pname).lower()
        if name_simple in found_simple or found_simple in name_simple:
            score += 10
        elif any(p in found_simple for p in name_simple.split() if len(p) > 2):
            score += 5

        score += min(user_count / 100000, 5)

        if score > best_score:
            best_score = score
            best = (pid, pname, club)

    return best if best_score > 0 else None


def search_player(name, nation):
    """Search Sofascore trying multiple name variants. Returns (id, name, club) or None."""
    for query in name_variants(name):
        try:
            data = fetch(f"https://api.sofascore.com/api/v1/search/players?q={urllib.parse.quote(query)}")
            time.sleep(0.2)
        except Exception:
            continue
        results = data.get("results", [])
        if not results:
            continue
        hit = score_results(results, name)
        if hit:
            return hit
    return None


def load_players():
    """Load player list from confirmed squads or fall back to StatsBomb summary."""
    players = []  # list of (name, nation)

    if SQUADS.exists():
        squads = json.loads(SQUADS.read_text())
        for nation, squad in squads.items():
            if nation == "pending" or not isinstance(squad, list):
                continue
            for p in squad:
                if isinstance(p, dict):
                    players.append((p.get("name", ""), nation))

    if not players:
        print("  [fallback] No confirmed squads yet — using StatsBomb player list")
        import pandas as pd
        sb = pd.read_parquet(SB_SUMM)
        # Only WC2026-participating nations
        wc_nations = {
            "Argentina","Australia","Belgium","Brazil","Canada","Colombia","Croatia",
            "Czech Republic","Ecuador","England","France","Germany","Ghana","Iran",
            "Japan","Mexico","Morocco","Netherlands","Panama","Paraguay","Portugal",
            "Qatar","Saudi Arabia","Scotland","Senegal","South Korea","Spain",
            "Switzerland","Tunisia","Turkey","United States","Uruguay",
        }
        for _, row in sb.iterrows():
            if row["team"] in wc_nations:
                players.append((row["player"], row["team"]))

    return players


def main():
    # Load existing map
    id_map = {}
    if OUT.exists():
        id_map = json.loads(OUT.read_text())

    players = load_players()
    print(f"Players to resolve: {len(players)}")
    print(f"Already in map: {len(id_map)}")

    new_found = 0
    not_found = []

    for name, nation in players:
        if not name or name in id_map:
            continue

        result = search_player(name, nation)
        time.sleep(0.4)

        if result:
            pid, found_name, club = result
            id_map[name] = {"id": pid, "sofascore_name": found_name, "club": club, "nation": nation}
            new_found += 1
            if new_found % 20 == 0:
                print(f"  [{new_found} found so far] last: {name} → {found_name} (id={pid})")
        else:
            not_found.append(f"{name} ({nation})")

    OUT.write_text(json.dumps(id_map, indent=2, ensure_ascii=False))

    print(f"\n{'='*50}")
    print(f"Resolved: {len(id_map)} players total ({new_found} new)")
    print(f"Not found: {len(not_found)}")
    if not_found[:10]:
        for p in not_found[:10]:
            print(f"  {p}")
    print(f"\nSaved → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
