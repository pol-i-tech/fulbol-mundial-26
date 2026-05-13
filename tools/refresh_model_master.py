#!/usr/bin/env python3
"""
Generate `db/masters/models.csv` by scanning `results/*/MODEL.md` files.

Each subdirectory of `results/` whose name does not start with `_` and
which contains a `MODEL.md` file becomes one row in the model master.
The MODEL.md `| Field | Value |` table at the top is parsed for human-
readable metadata; anything missing falls back to sensible defaults.

Idempotent. Safe to re-run when new models land or MODEL.md files change.

Usage:
    python3 tools/refresh_model_master.py
    python3 tools/refresh_model_master.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "db" / "masters" / "models.csv"
RESULTS_DIR = ROOT / "results"

# Match "| **Key** | Value |" rows in the MODEL.md header table.
FIELD_RE = re.compile(r"^\s*\|\s*\*\*([^|*]+?)\*\*\s*\|\s*(.+?)\s*\|\s*$")


def parse_model_md(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = FIELD_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()
        fields[key] = val
    return fields


def classify_model_type(model_id: str, fields: dict[str, str]) -> str:
    """Heuristic: classify model based on dir name and MODEL.md content."""
    if "baseline" in model_id:
        return "baseline"
    if "ensemble" in model_id or "compound" in model_id:
        return "compound"
    if model_id == "manual-tier-list":
        return "human"
    if model_id == "wc2026-sim":
        return "simulation"
    return "single-source"


def discover_models() -> list[dict]:
    if not RESULTS_DIR.exists():
        return []
    rows = []
    for child in sorted(RESULTS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_") or child.name == "comparisons":
            continue
        model_md = child / "MODEL.md"
        if not model_md.exists():
            continue
        fields = parse_model_md(model_md)
        model_id = child.name
        # Detect methodology path
        method_dir = ROOT / "methodology" / model_id
        method_rel = (
            str(method_dir.relative_to(ROOT)) if method_dir.exists() else ""
        )
        rows.append(
            {
                "model_id": model_id,
                "model_name": fields.get("model_name", model_id),
                "model_type": classify_model_type(model_id, fields),
                "methodology_path": method_rel,
                "results_path": str(child.relative_to(ROOT)),
                "last_validation_status": fields.get("validation_status", ""),
            }
        )
    return rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    rows = discover_models()
    if not rows:
        print("ERROR: no MODEL.md files found under results/", file=sys.stderr)
        return 1

    df = pd.DataFrame(rows).sort_values("model_id").reset_index(drop=True)
    print(f"[model-master] {len(df)} models found")
    for _, r in df.iterrows():
        print(f"    {r['model_id']:<24}  {r['model_type']:<14}  {r['model_name']}")

    if args.dry_run:
        print("[model-master] dry-run: not writing")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, lineterminator="\n")
    print(f"[model-master] wrote {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
