#!/usr/bin/env python3
"""
Validate model prediction snapshots.

Examples:
  python3 tools/validate_predictions.py --all
  python3 tools/validate_predictions.py results/elo-baseline/2026-04-28/predictions.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

EXPECTED_COLUMNS = [
    "as_of_date",
    "match_id",
    "market_type",
    "outcome",
    "p_model",
    "confidence",
    "model_version",
    "notes",
]

MARKET_TYPES = {
    "match_1x2",
    "outright_winner",
    "group_winner",
    "team_advances",
    "top_scorer",
    "totals",
    "btts",
}

SUM_TO_ONE_MARKETS = {
    "match_1x2",
    "outright_winner",
    "group_winner",
    "totals",
    "btts",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIFA3_RE = re.compile(r"^[A-Z]{3}$")
GROUP_RE = re.compile(r"^GROUP-[A-L]-WC2026$")
GROUP_MATCH_RE = re.compile(r"^WC26-[A-Z]{3}-[A-Z]{3}-\d{4}-\d{2}-\d{2}$")
# Slot-based knockout IDs (e.g. WC26-R32-08, WC26-F): pre-tournament bracket
# placeholders for outputs that emit one row per bracket slot.
KNOCKOUT_SLOT_RE = re.compile(r"^WC26-(R32|R16|QF|SF)-\d{2}$|^WC26-F$")
# Pair-based knockout IDs (e.g. WC26-R32-FRA-GER, WC26-FINAL-BRA-ESP): emitted
# by the MC simulator for every actually-occurring team-pair at each stage.
KNOCKOUT_PAIR_RE = re.compile(r"^WC26-(R32|R16|QF|SF|FINAL)-[A-Z]{3}-[A-Z]{3}$")
ADVANCE_RE = re.compile(r"^ADVANCE-[A-Z]{3}-WC2026$")
TOTALS_RE = re.compile(r"^(over|under)_[0-9]+(_[0-9]+)?$")


@dataclass
class Issue:
    path: Path
    message: str
    row: int | None = None

    def format(self) -> str:
        rel = self.path.relative_to(ROOT) if self.path.is_absolute() else self.path
        prefix = f"{rel}"
        if self.row is not None:
            prefix += f": row {self.row}"
        return f"{prefix}: {self.message}"


def is_date_snapshot(path: Path) -> bool:
    return DATE_RE.match(path.parent.name) is not None


def discover_prediction_files(include_backtests: bool) -> list[Path]:
    paths = sorted(ROOT.glob("results/*/*/predictions.csv"))
    paths = [p for p in paths if "_template" not in p.parts]
    if not include_backtests:
        paths = [p for p in paths if is_date_snapshot(p)]
    return paths


def valid_match_id(match_id: str) -> bool:
    return (
        GROUP_MATCH_RE.match(match_id) is not None
        or KNOCKOUT_SLOT_RE.match(match_id) is not None
        or KNOCKOUT_PAIR_RE.match(match_id) is not None
        or match_id == "OUTRIGHT-WC2026"
        or GROUP_RE.match(match_id) is not None
        or ADVANCE_RE.match(match_id) is not None
        or match_id == "GOLDENBOOT-WC2026"
    )


def parse_probability(value: str) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def valid_confidence(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"high", "medium", "low"}:
        return True
    number = parse_probability(value)
    return number is not None and 0 <= number <= 1


def validate_outcome(market_type: str, outcome: str) -> str | None:
    if market_type == "match_1x2" and outcome not in {"home", "draw", "away"}:
        return "match_1x2 outcome must be home, draw, or away"
    if market_type in {"outright_winner", "group_winner"}:
        if not (FIFA3_RE.match(outcome) or outcome == "OTHER"):
            return f"{market_type} outcome must be a 3-letter FIFA code"
    if market_type == "team_advances" and outcome not in {"yes", "no"}:
        return "team_advances outcome must be yes or no"
    if market_type == "totals" and TOTALS_RE.match(outcome) is None:
        return "totals outcome should look like over_2_5 or under_2_5"
    if market_type == "btts" and outcome not in {"yes", "no"}:
        return "btts outcome must be yes or no"
    if market_type == "top_scorer" and not outcome.strip():
        return "top_scorer outcome must be a player name"
    return None


def validate_file(path: Path, strict_header: bool) -> list[Issue]:
    issues: list[Issue] = []
    path = path.resolve()

    if not path.exists():
        return [Issue(path, "file does not exist")]

    if is_date_snapshot(path):
        model_card = path.parent.parent / "MODEL.md"
        if not model_card.exists():
            issues.append(Issue(path, f"missing model card at {model_card.relative_to(ROOT)}"))

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    if strict_header and fieldnames != EXPECTED_COLUMNS:
        issues.append(
            Issue(path, f"header must be exactly {EXPECTED_COLUMNS}; got {fieldnames}")
        )

    if not rows:
        issues.append(Issue(path, "file has no prediction rows"))
        return issues

    folder_date = path.parent.name
    sums: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)

    for idx, row in enumerate(rows, start=2):
        as_of_date = (row.get("as_of_date") or "").strip()
        match_id = (row.get("match_id") or "").strip()
        market_type = (row.get("market_type") or "").strip()
        outcome = (row.get("outcome") or "").strip()
        confidence = (row.get("confidence") or "").strip()
        model_version = (row.get("model_version") or "").strip()
        p_model_raw = (row.get("p_model") or "").strip()

        if is_date_snapshot(path) and as_of_date != folder_date:
            issues.append(Issue(path, f"as_of_date {as_of_date!r} must match folder {folder_date!r}", idx))
        if not DATE_RE.match(as_of_date):
            issues.append(Issue(path, f"as_of_date {as_of_date!r} is not YYYY-MM-DD", idx))
        if market_type not in MARKET_TYPES:
            issues.append(Issue(path, f"unknown market_type {market_type!r}", idx))
        if not valid_match_id(match_id):
            issues.append(Issue(path, f"match_id {match_id!r} does not follow project conventions", idx))

        outcome_issue = validate_outcome(market_type, outcome)
        if outcome_issue:
            issues.append(Issue(path, outcome_issue, idx))

        p_model = parse_probability(p_model_raw)
        if p_model is None:
            issues.append(Issue(path, f"p_model {p_model_raw!r} is not a number", idx))
        elif not 0 <= p_model <= 1:
            issues.append(Issue(path, f"p_model {p_model} is outside [0, 1]", idx))
        elif market_type in SUM_TO_ONE_MARKETS:
            key = (match_id, market_type)
            sums[key] += p_model
            counts[key] += 1

        if not valid_confidence(confidence):
            issues.append(Issue(path, f"confidence {confidence!r} must be high/medium/low or numeric [0, 1]", idx))
        if not model_version:
            issues.append(Issue(path, "model_version is required", idx))

    for (match_id, market_type), total in sums.items():
        if not 0.99 <= total <= 1.01:
            issues.append(
                Issue(
                    path,
                    f"probabilities for ({match_id}, {market_type}) sum to {total:.4f}, expected 0.99..1.01",
                )
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate project prediction CSV files.")
    parser.add_argument("paths", nargs="*", type=Path, help="Prediction CSV paths to validate.")
    parser.add_argument("--all", action="store_true", help="Validate all date-snapshot predictions under results/.")
    parser.add_argument(
        "--include-backtests",
        action="store_true",
        help="Include non-date folders such as wc2022-backtest. These often contain diagnostic schemas.",
    )
    parser.add_argument(
        "--lenient-header",
        action="store_true",
        help="Do not require the exact 8-column snapshot schema.",
    )
    args = parser.parse_args()

    if args.all:
        paths = discover_prediction_files(include_backtests=args.include_backtests)
    else:
        paths = [p if p.is_absolute() else ROOT / p for p in args.paths]

    if not paths:
        print("No prediction files selected.", file=sys.stderr)
        return 2

    issues: list[Issue] = []
    for path in paths:
        strict_header = not args.lenient_header and is_date_snapshot(path)
        issues.extend(validate_file(path, strict_header=strict_header))

    if issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        print(f"\nValidation failed: {len(issues)} issue(s) across {len(paths)} file(s).", file=sys.stderr)
        return 1

    print(f"Validation passed: {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
