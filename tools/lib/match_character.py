"""Qualitative 'match character' from a match's model outputs.

Pure function, no I/O — turns the engine's per-match numbers into readable
labels used by both `per_game.csv` and `REPORT.md`. Every adjective the report
prints ("open", "tight", "coin-flip", "penalties") traces back to a number here.

Two ideas combine into the character:

  1. Model agreement (the WC2022 backtest "disagreement taxonomy"). The ensemble
     is `0.35·Elo + 0.45·xG-Poisson + 0.20·Form`. When all three component models
     pick the same 1X2 outcome → "golden-zone" (in the WC2022 backtest these went
     15/15, even at 48% confidence). All three different → "3-way-split", a genuine
     coin-flip where the ensemble average is just noise.
     See docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md

  2. The shape of *this* prediction: how open (expected goals) and how decisive
     (gap between the two win probabilities) the match looks.

NOTE ON THRESHOLDS: the cutoffs below (GOAL_FEST_XG, COMFORTABLE_MARGIN, ...) are
PRESENTATIONAL classification boundaries for prose. They are NOT predictive model
weights or priors — they do not feed `ensemble_probs` and changing them cannot
change who the model predicts to win, only how the match is described.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── presentational thresholds (prose only — NOT modeling weights) ──────────────
# Openness cutoffs are calibrated to THIS engine's expected-goals range (its
# Poisson lambdas run conservative, total xG ~0.8-2.9 across the slate), so the
# label discriminates *relative to the tournament's own matches* rather than to
# an absolute goals-per-game scale. The top tier is "open", not "goal-fest",
# precisely because a 2.1-xG game isn't a goal-fest in absolute terms.
OPEN_XG = 2.1            # total expected goals at/above this → "open"
LOW_SCORING_XG = 1.5     # below this → "low-scoring grind"; between → "balanced"
COMFORTABLE_MARGIN = 0.25  # |p_home - p_away| at/above this → "comfortable"
COMPETITIVE_MARGIN = 0.05  # at/above this → "competitive"; below → "coin-flip"
EVEN_MARGIN = 0.04         # |p_home - p_away| below this → favorite is "even"

OUTCOMES = ("H", "D", "A")


@dataclass(frozen=True)
class MatchCharacter:
    favorite: str          # 'home' | 'away' | 'even'
    confidence_band: str   # 'golden-zone' | '2-way-split' | '3-way-split'
    openness: str          # 'open' | 'balanced' | 'low-scoring grind'
    decisiveness: str      # 'comfortable' | 'competitive' | 'coin-flip'
    descriptor: str        # one-line human phrase for the report


def _confidence_band(model_picks: tuple[str, str, str]) -> str:
    """Agreement across the three component-model 1X2 picks (Elo, Poisson, Form)."""
    distinct = set(model_picks)
    if len(distinct) == 1:
        return "golden-zone"
    if len(distinct) == 3:
        return "3-way-split"
    return "2-way-split"


def _favorite(p_home: float, p_away: float) -> str:
    if abs(p_home - p_away) < EVEN_MARGIN:
        return "even"
    return "home" if p_home > p_away else "away"


def _openness(total_xg: float) -> str:
    if total_xg >= OPEN_XG:
        return "open"
    if total_xg < LOW_SCORING_XG:
        return "low-scoring grind"
    return "balanced"


def _decisiveness(p_home: float, p_away: float) -> str:
    # Round to absorb float noise so values sitting exactly on a threshold
    # (e.g. 0.45 - 0.40 = 0.04999…) classify on the intuitive side.
    margin = round(abs(p_home - p_away), 6)
    if margin >= COMFORTABLE_MARGIN:
        return "comfortable"
    if margin >= COMPETITIVE_MARGIN:
        return "competitive"
    return "coin-flip"


def _descriptor(c_band: str, openness: str, decisiveness: str, knockout: bool) -> str:
    """Stitch the labels into one readable phrase the report can print verbatim."""
    if decisiveness == "coin-flip":
        tail = (
            "a coin-flip that could go to extra time or penalties"
            if knockout
            else "a coin-flip that could easily end level"
        )
    elif decisiveness == "competitive":
        tail = "a competitive, winnable-either-way match"
    else:  # comfortable
        tail = "a comfortable edge for the favorite"

    if openness == "open":
        head = "An open, end-to-end affair"
    elif openness == "low-scoring grind":
        head = "A tight, low-scoring grind"
    else:
        head = "A balanced contest"

    # Golden-zone overrides the hedging: all three signals point one way.
    if c_band == "golden-zone" and decisiveness != "coin-flip":
        return f"{head} — all three models agree, {tail}."
    if c_band == "3-way-split":
        return f"{head} — the models can't agree, {tail}."
    return f"{head} — {tail}."


def classify_match(
    p_home: float,
    p_draw: float,
    p_away: float,
    lam_home: float,
    lam_away: float,
    model_picks: tuple[str, str, str],
    knockout: bool = False,
) -> MatchCharacter:
    """Classify one match.

    Args:
        p_home/p_draw/p_away: ensemble 1X2 probabilities (need not be exactly
            normalized; only the home-vs-away gap and draw share are used).
        lam_home/lam_away: expected goals for each side (Poisson lambdas).
        model_picks: the 1X2 pick ('H'/'D'/'A') of each component model, in any
            order — (Elo, Poisson, Form). Used for the agreement band.
        knockout: True for knockout ties (changes coin-flip wording to penalties).
    """
    band = _confidence_band(model_picks)
    fav = _favorite(p_home, p_away)
    openness = _openness(lam_home + lam_away)
    decisiveness = _decisiveness(p_home, p_away)
    descriptor = _descriptor(band, openness, decisiveness, knockout)
    return MatchCharacter(
        favorite=fav,
        confidence_band=band,
        openness=openness,
        decisiveness=decisiveness,
        descriptor=descriptor,
    )
