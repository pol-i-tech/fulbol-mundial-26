"""
Shared name and country normalization utilities for the player matching layer.

Single source of truth used by:
  - tools/refresh_player_master.py (master maintenance)
  - tools/match_sources_to_masters.py (source-to-dim matching)

Read-only functions; deterministic; safe to import anywhere.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

# Re-export FIFA code mappings from weekly_pull so the project has one
# authoritative team-code dictionary. Anything mapping a country name or
# ISO2 to FIFA3 should route through here.
_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from weekly_pull import NAME_TO_FIFA3, ISO2_TO_FIFA3  # noqa: E402


# Supplement for FIFA codes that aren't WC2026 qualifiers but appear in
# the player parquets (Understat covers all of European football, so e.g.
# Hungary or Slovenia players show up even when they don't qualify).
# Kept here, not in weekly_pull.py, because weekly_pull is scoped to the
# betting/markets pipeline; this dict is owned by the analytics layer.
_DB_LAYER_NAME_SUPPLEMENT = {
    "Albania": "ALB",
    "Chile": "CHI",
    "Georgia": "GEO",
    "Hungary": "HUN",
    "Peru": "PER",
    "Poland": "POL",
    "Romania": "ROU",
    "Slovakia": "SVK",
    "Slovenia": "SVN",
    "Venezuela": "VEN",
    "Greece": "GRE",
    "Russia": "RUS",
    "Bulgaria": "BUL",
    "Finland": "FIN",
    "Iceland": "ISL",
    "Israel": "ISR",
    "Luxembourg": "LUX",
    "Albania": "ALB",
    "Andorra": "AND",
    "Moldova": "MDA",
    "Belarus": "BLR",
    "Estonia": "EST",
    "Latvia": "LVA",
    "Lithuania": "LTU",
    "Montenegro": "MNE",
    "Kosovo": "KOS",
    "Armenia": "ARM",
    "Azerbaijan": "AZE",
    "Cyprus": "CYP",
    "Malta": "MLT",
    "Faroe Islands": "FRO",
    "Liechtenstein": "LIE",
    "San Marino": "SMR",
    "Gibraltar": "GIB",
    "Kazakhstan": "KAZ",
}

def _accent_strip(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


# Pre-build a normalized lookup so case/whitespace/accent variants all resolve.
# E.g., "Türkiye", "turkiye", "TURKEY" all map to TUR via the "turkey" key.
_NAME_TO_FIFA3_NORM = {
    **{_accent_strip(k).strip().lower(): v for k, v in NAME_TO_FIFA3.items()},
    **{_accent_strip(k).strip().lower(): v for k, v in _DB_LAYER_NAME_SUPPLEMENT.items()},
}
# Also add an explicit alias for Türkiye → TUR (the modernized country name)
_NAME_TO_FIFA3_NORM["turkiye"] = "TUR"
_ISO2_TO_FIFA3_NORM = {k.strip().upper(): v for k, v in ISO2_TO_FIFA3.items()}


def normalize(name: str) -> str:
    """Normalize a player name for matching.

    Steps: NFKD unicode decomposition → strip accents → lowercase →
    collapse internal whitespace → remove non-alphanumeric (except spaces
    and hyphens).

    Deterministic; same input always returns same output.
    """
    if name is None:
        return ""
    # Strip accents via NFKD then drop combining characters
    nfkd = unicodedata.normalize("NFKD", str(name))
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    lowered = ascii_only.lower().strip()
    # Replace any non-alphanumeric (except space/hyphen) with space
    stripped = re.sub(r"[^a-z0-9\s\-]", " ", lowered)
    # Collapse internal whitespace
    collapsed = re.sub(r"\s+", " ", stripped).strip()
    return collapsed


def normalize_country(value: str) -> Optional[str]:
    """Resolve a country reference to its FIFA 3-letter code.

    Accepts:
      - FIFA 3-letter codes (returned unchanged when already canonical)
      - ISO 3166-1 alpha-2 codes
      - Country display names matching NAME_TO_FIFA3 keys (case-insensitive)

    Returns None if no mapping is found.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    # Already a FIFA3 code?
    if len(s) == 3 and s.upper() == s and s.isalpha():
        # Heuristic: treat 3-letter uppercase alpha as FIFA3; let caller verify.
        return s.upper()

    # ISO2?
    if len(s) == 2 and s.isalpha():
        return _ISO2_TO_FIFA3_NORM.get(s.upper())

    # Display name (case- and accent-insensitive).
    return _NAME_TO_FIFA3_NORM.get(_accent_strip(s).lower())


def derive_birth_year(birth_date: Optional[str]) -> Optional[int]:
    """Parse a YYYY-MM-DD date string to an int year; None when blank/invalid."""
    if not birth_date:
        return None
    s = str(birth_date).strip()
    if len(s) < 4 or not s[:4].isdigit():
        return None
    year = int(s[:4])
    if 1900 <= year <= 2030:
        return year
    return None
