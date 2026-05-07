#!/usr/bin/env python3
"""
Pull 2026 match statistics for WC2026 squad players from Sofascore.

For each resolved player, fetches all matches played since Jan 1 2026
and extracts xG, shots, goals, assists, key passes, and minutes played.

Input:  data/raw/sofascore/player_id_map.json
Output: data/raw/sofascore/players/{player_id}_2026.json  (per player)
        data/derived/sofascore_2026_player_xg.parquet

Usage:
  python3 tools/pull_sofascore_2026_stats.py
"""
import json, time, datetime, urllib.request
from pathlib import Path

import pandas as pd

ROOT    = Path(__file__).parent.parent
ID_MAP  = ROOT / "data" / "raw" / "sofascore" / "player_id_map.json"
RAW_DIR = ROOT / "data" / "raw" / "sofascore" / "players"
DERIVED = ROOT / "data" / "derived"
RAW_DIR.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)

JAN_2026 = int(datetime.datetime(2026, 1, 1).timestamp())
MAX_XG90 = 6.0
MIN_MINS  = 90

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.sofascore.com/",
    "Accept": "application/json, */*",
}


def fetch(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                wait = 10 * (attempt + 1)
                print(f"    [rate limit] waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    return {}


def get_2026_matches(player_id):
    """Return list of 2026 match events for a player."""
    try:
        data = fetch(f"https://api.sofascore.com/api/v1/player/{player_id}/events/last/0")
        return [m for m in data.get("events", [])
                if m.get("startTimestamp", 0) >= JAN_2026]
    except Exception:
        return []


def get_match_stats(player_id, match_id):
    """Return stats dict for a player in a specific match."""
    try:
        data = fetch(f"https://api.sofascore.com/api/v1/event/{match_id}/player/{player_id}/statistics")
        return data.get("statistics", {})
    except Exception:
        return {}


def pull_player(name, player_id, nation):
    cache = RAW_DIR / f"{player_id}_2026.json"

    # Use cache if recent (< 7 days)
    if cache.exists():
        age_days = (datetime.datetime.now().timestamp() - cache.stat().st_mtime) / 86400
        if age_days < 7:
            return json.loads(cache.read_text()), "cached"

    matches = get_2026_matches(player_id)
    if not matches:
        return [], "no_matches"

    records = []
    for m in matches:
        time.sleep(0.25)
        mid  = m["id"]
        ts   = datetime.datetime.fromtimestamp(m["startTimestamp"]).strftime("%Y-%m-%d")
        comp = m.get("tournament", {}).get("name", "")
        home = m.get("homeTeam", {}).get("name", "")
        away = m.get("awayTeam", {}).get("name", "")

        s = get_match_stats(player_id, mid)
        if not s:
            continue

        mins   = s.get("minutesPlayed", 0)
        xg     = s.get("expectedGoals")
        shots  = s.get("totalShots", 0)
        goals  = s.get("goals", 0)
        assist = s.get("goalAssist", 0)
        kpass  = s.get("keyPass", 0)
        rating = s.get("rating")

        # Fallback if xG not available: shots × 0.1
        xg_used = float(xg) if xg is not None else (shots * 0.10)
        xg_source = "sofascore" if xg is not None else "shots_proxy"

        records.append({
            "match_id":   mid,
            "date":       ts,
            "competition":comp,
            "home":       home,
            "away":       away,
            "minutes":    mins,
            "xg":         round(xg_used, 4),
            "xg_source":  xg_source,
            "shots":      shots,
            "goals":      goals,
            "assists":    assist,
            "key_passes": kpass,
            "rating":     rating,
        })

    cache.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    return records, "fetched"


def aggregate(name, nation, records):
    """Compute 2026 per-90 stats from match records."""
    if not records:
        return None

    total_mins   = sum(r["minutes"] for r in records)
    total_xg     = sum(r["xg"] for r in records)
    total_shots  = sum(r["shots"] for r in records)
    total_goals  = sum(r["goals"] for r in records)
    total_assists= sum(r["assists"] for r in records)
    total_kpass  = sum(r["key_passes"] for r in records)
    ratings      = [r["rating"] for r in records if r["rating"] is not None]
    matches_used = len(records)

    if total_mins < MIN_MINS:
        return None  # not enough data

    per90 = 90 / total_mins
    xg90  = round(total_xg * per90, 4)

    # Apply Sarabia rule
    if xg90 > MAX_XG90:
        return None

    return {
        "name":           name,
        "nation":         nation,
        "matches_2026":   matches_used,
        "minutes_2026":   total_mins,
        "xg_2026":        round(total_xg, 3),
        "xg_per_90":      xg90,
        "shots_per_90":   round(total_shots * per90, 3),
        "goals_per_90":   round(total_goals * per90, 3),
        "assists_per_90": round(total_assists * per90, 3),
        "kpass_per_90":   round(total_kpass * per90, 3),
        "avg_rating":     round(sum(ratings)/len(ratings), 2) if ratings else None,
    }


def main():
    if not ID_MAP.exists():
        print("No player_id_map.json found. Run resolve_sofascore_ids.py first.")
        return

    id_map = json.loads(ID_MAP.read_text())
    print(f"Players in ID map: {len(id_map)}")

    rows = []
    fetched = cached = no_data = flagged = 0

    for name, info in id_map.items():
        pid    = info["id"]
        nation = info.get("nation", "")

        records, status = pull_player(name, pid, nation)
        time.sleep(1.0)

        agg = aggregate(name, nation, records)

        if status == "cached":
            cached += 1
        elif status == "fetched":
            fetched += 1
        else:
            no_data += 1

        if agg is None:
            if records:
                flagged += 1
            continue

        rows.append(agg)

    if not rows:
        print("\n[warn] No player data collected — likely rate-limited. Re-run in a few minutes.")
        return

    df = pd.DataFrame(rows).sort_values(["nation", "xg_per_90"], ascending=[True, False])
    df.to_parquet(DERIVED / "sofascore_2026_player_xg.parquet", index=False)

    print(f"\n{'='*60}")
    print(f"Fetched: {fetched}  Cached: {cached}  No data: {no_data}  Flagged: {flagged}")
    print(f"Players with valid 2026 ratings: {len(df)}")
    print(f"\nTop 20 by xG/90 in 2026:")
    print(f"{'Player':<28} {'Nation':<18} {'xG/90':>7} {'Goals':>6} {'Mins':>6} {'Matches':>8} {'Rating':>7}")
    print("-"*80)
    for _, r in df.head(20).iterrows():
        rat = str(r["avg_rating"]) if r["avg_rating"] else "—"
        print(f"  {r['name']:<26} {r['nation']:<18} {r['xg_per_90']:>7} {r['goals_per_90']:>6.2f} "
              f"{r['minutes_2026']:>6} {r['matches_2026']:>8} {rat:>7}")

    print(f"\nSaved → data/derived/sofascore_2026_player_xg.parquet ({len(df)} players)")


if __name__ == "__main__":
    main()
