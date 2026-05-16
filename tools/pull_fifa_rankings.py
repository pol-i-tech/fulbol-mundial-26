#!/usr/bin/env python3
"""
Pull the current FIFA Men's World Ranking from Wikipedia's authoritative data module.

Source: Wikipedia Module:SportsRankings/data/FIFA_World_Rankings
        https://en.wikipedia.org/wiki/Module:SportsRankings/data/FIFA_World_Rankings

Why Wikipedia and not inside.fifa.com directly?
  inside.fifa.com is a Next.js SPA that hydrates rankings client-side; its
  /api/ranking-overview endpoint returns an empty array to non-browser clients.
  The Wikipedia module is updated within hours of every official FIFA ranking
  edition (~6x/year), powers the Wikipedia top-20 table on the FIFA Men's World
  Ranking article, and contains all 211 ranked teams in a stable Lua-table
  format that is trivial to parse.

Output:
  data/raw/fifa_rankings/<YYYY-MM-DD>/ranking_module.json
    -- raw Wikipedia API response (preserves wikitext for audit/diff)

The cleaner (tools/build_country_features.py) parses the Lua wikitext into rows
and writes the curated parquet.

Usage:
    python3 tools/pull_fifa_rankings.py
    python3 tools/pull_fifa_rankings.py --date 2026-05-14
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "fifa_rankings"

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
MODULE_PAGE = "Module:SportsRankings/data/FIFA_World_Rankings"
USER_AGENT = "fulbol-mundial-26/fifa-rankings-fetcher (+https://github.com/) python-urllib"


def fetch_module() -> dict:
    """Return the parsed Wikipedia API response containing the module's wikitext."""
    params = (
        f"action=parse&page={urllib.request.quote(MODULE_PAGE)}"
        "&format=json&prop=wikitext"
    )
    url = f"{WIKIPEDIA_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    payload = json.loads(body)
    if "error" in payload:
        raise RuntimeError(f"Wikipedia API error: {payload['error']}")
    wikitext = payload.get("parse", {}).get("wikitext", {}).get("*", "")
    if not wikitext or "data.rankings" not in wikitext:
        raise RuntimeError(
            "Wikipedia module response is missing 'data.rankings' block -- "
            "the module page may have moved or its schema changed"
        )
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--date", default=_date.today().isoformat(),
                   help="Snapshot date dir (default: today). Format: YYYY-MM-DD.")
    args = p.parse_args()

    out_dir = RAW_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ranking_module.json"

    try:
        payload = fetch_module()
    except urllib.error.HTTPError as e:
        print(f"[error] Wikipedia HTTP {e.code}: {e.reason}", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"[error] Wikipedia network: {e.reason}", file=sys.stderr)
        return 2

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    wikitext = payload["parse"]["wikitext"]["*"]
    n_rows = wikitext.count("\n          {")  # one row per ranking line
    print(f"[ok] fifa rankings: ~{n_rows} teams -> {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
