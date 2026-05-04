#!/usr/bin/env python3
"""
Pull official WC2026 squad lists from Wikipedia.

Scrapes each nation's WC2026 Wikipedia page for their confirmed 26-player squad.
Run daily from ~May 20 until all 48 nations are confirmed (FIFA deadline May 29).

Saves:
  data/raw/squads/wc2026_squads_confirmed.json

Usage:
  python3 tools/pull_wc2026_final_squads.py
"""
import json, re, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "data" / "raw" / "squads" / "wc2026_squads_confirmed.json"

WC2026_NATIONS = [
    "Mexico", "South Africa", "Czechia", "South Korea",
    "Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland",
    "Brazil", "Morocco", "Haiti", "Scotland",
    "USA", "Paraguay", "Australia", "Türkiye",
    "Germany", "Curaçao", "Ivory Coast", "Ecuador",
    "Netherlands", "Japan", "Sweden", "Tunisia",
    "Belgium", "Egypt", "Iran", "New Zealand",
    "Spain", "Cape Verde", "Saudi Arabia", "Uruguay",
    "France", "Senegal", "Iraq", "Norway",
    "Argentina", "Algeria", "Austria", "Jordan",
    "Portugal", "DR Congo", "Uzbekistan", "Colombia",
    "England", "Croatia", "Ghana", "Panama",
]

WIKI_NAME = {
    "USA":                      "United_States",
    "Czechia":                  "Czech_Republic",
    "Türkiye":                  "Turkey",
    "Ivory Coast":              "Ivory_Coast",
    "DR Congo":                 "DR_Congo",
    "Bosnia and Herzegovina":   "Bosnia_and_Herzegovina",
    "South Africa":             "South_Africa",
    "Cape Verde":               "Cape_Verde",
    "New Zealand":              "New_Zealand",
    "Saudi Arabia":             "Saudi_Arabia",
    "South Korea":              "South_Korea",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WC2026-research/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}


def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_squad(html, nation):
    """Extract player rows from Wikipedia squad table."""
    # Look for squad table — Wikipedia uses wikitable class
    # Pattern: rows with position code (GK/DF/MF/FW) and player name
    players = []

    # Try to find the squad table section
    pos_pattern = re.compile(
        r'<tr[^>]*>.*?'
        r'(GK|DF|MF|FW|G|D|M|F)\b.*?'
        r'title="([^"]+)"[^>]*>([^<]+)</a>.*?'
        r'</tr>',
        re.DOTALL | re.IGNORECASE
    )

    # Simpler fallback: look for any table row with a position code
    row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    cell_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL)
    clean_pattern = re.compile(r'<[^>]+>')

    for row_match in row_pattern.finditer(html):
        row = row_match.group(1)
        cells = [clean_pattern.sub('', c.group(1)).strip()
                 for c in cell_pattern.finditer(row)]
        cells = [c.replace('\n', ' ').strip() for c in cells if c.strip()]

        if not cells:
            continue
        # Check if first cell looks like a position code
        if cells[0].upper() in ('GK', 'DF', 'MF', 'FW', 'G', 'D', 'M', 'F'):
            pos = cells[0].upper()
            if pos == 'G': pos = 'GK'
            if pos == 'D': pos = 'DF'
            if pos == 'M': pos = 'MF'
            if pos == 'F': pos = 'FW'

            # Player name is usually the 3rd or 4th cell (after no., pos, name)
            name = None
            club = None
            for i, cell in enumerate(cells[1:], 1):
                if len(cell) > 2 and not cell.isdigit() and name is None:
                    name = cell
                elif name is not None and len(cell) > 1:
                    club = cell
                    break

            if name and len(name) > 2:
                players.append({
                    "name":     name,
                    "position": pos,
                    "club":     club or "",
                })

    return players


def pull_nation(nation):
    wiki_name = WIKI_NAME.get(nation, nation.replace(" ", "_"))
    url = f"https://en.wikipedia.org/wiki/{wiki_name}_at_the_2026_FIFA_World_Cup"
    try:
        html = fetch_html(url)
        if "Wikipedia does not have an article" in html or "404" in html[:200]:
            return None, "no_page"
        players = parse_squad(html, nation)
        if len(players) >= 10:
            return players, "confirmed"
        elif len(players) > 0:
            return players, "partial"
        else:
            return None, "no_table"
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}"
    except Exception as e:
        return None, f"error_{type(e).__name__}"


def main():
    existing = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text())

    confirmed = {k: v for k, v in existing.items() if k != "pending"}
    pending   = []
    status    = {}

    print(f"Pulling WC2026 squads from Wikipedia ({len(WC2026_NATIONS)} nations)...\n")

    for nation in WC2026_NATIONS:
        if nation in confirmed:
            print(f"  [cache]   {nation:<30} {len(confirmed[nation])} players")
            status[nation] = "cached"
            continue

        players, result = pull_nation(nation)
        time.sleep(0.8)

        if result == "confirmed":
            confirmed[nation] = players
            status[nation] = "confirmed"
            print(f"  [ok]      {nation:<30} {len(players)} players")
        elif result == "partial":
            confirmed[nation] = players
            status[nation] = "partial"
            print(f"  [partial] {nation:<30} {len(players)} players (may be incomplete)")
        else:
            pending.append(nation)
            status[nation] = result
            print(f"  [pending] {nation:<30} ({result})")

    out = {**confirmed, "pending": pending}
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    n_confirmed = len([n for n in WC2026_NATIONS if n not in pending])
    print(f"\n{'='*50}")
    print(f"Confirmed: {n_confirmed}/48 nations")
    print(f"Pending:   {len(pending)} nations")
    if pending:
        print(f"  {', '.join(pending)}")
    print(f"\nSaved → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
