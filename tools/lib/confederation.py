"""WC2026 confederation lookup, keyed on the display nation names ESPN uses.

Single source of truth for `confederation` per nation. Imported by both
`tools/pull_wc2026_squads.py` (Wikipedia path, still uses its own dict but
should migrate here) and the new `tools/build_wc2026_squads_clean.py`.

The map covers the 48 WC2026 qualifiers plus alternative spellings ESPN
uses (e.g., "United States" vs "USA", "Bosnia-Herzegovina" vs
"Bosnia and Herzegovina").
"""
from __future__ import annotations

CONFEDERATION_BY_NATION: dict[str, str] = {
    # CONMEBOL
    "Argentina": "CONMEBOL", "Brazil": "CONMEBOL", "Colombia": "CONMEBOL",
    "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL", "Uruguay": "CONMEBOL",
    # CONCACAF
    "Canada": "CONCACAF", "Curaçao": "CONCACAF", "Curacao": "CONCACAF",
    "Haiti": "CONCACAF", "Mexico": "CONCACAF", "Panama": "CONCACAF",
    "United States": "CONCACAF", "USA": "CONCACAF",
    # AFC
    "Australia": "AFC", "Iran": "AFC", "Iraq": "AFC", "Japan": "AFC",
    "Jordan": "AFC", "Qatar": "AFC", "Saudi Arabia": "AFC",
    "South Korea": "AFC", "Uzbekistan": "AFC",
    # CAF
    "Algeria": "CAF", "Cape Verde": "CAF", "DR Congo": "CAF",
    "Congo DR": "CAF", "Egypt": "CAF", "Ghana": "CAF", "Ivory Coast": "CAF",
    "Morocco": "CAF", "Senegal": "CAF", "South Africa": "CAF",
    "Tunisia": "CAF",
    # OFC
    "New Zealand": "OFC",
    # UEFA
    "Austria": "UEFA", "Belgium": "UEFA",
    "Bosnia and Herzegovina": "UEFA", "Bosnia-Herzegovina": "UEFA",
    "Croatia": "UEFA", "Czech Republic": "UEFA", "Czechia": "UEFA",
    "England": "UEFA", "France": "UEFA", "Germany": "UEFA",
    "Netherlands": "UEFA", "Norway": "UEFA", "Portugal": "UEFA",
    "Scotland": "UEFA", "Spain": "UEFA", "Sweden": "UEFA",
    "Switzerland": "UEFA", "Turkey": "UEFA", "Türkiye": "UEFA",
}

# ESPN-display-name → canonical-name used by `normalize_country()`.
# normalize_country() doesn't know all of ESPN's spellings out of the box,
# so the cleaner remaps these before resolving FIFA3.
ESPN_NATION_ALIASES: dict[str, str] = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Congo DR": "DR Congo",
    "Curacao": "Curaçao",
    "United States": "USA",
}


def confederation_for(nation: str) -> str | None:
    return CONFEDERATION_BY_NATION.get(nation)
