"""Pre-flight cost gate for the daily Orchestrator run.

Sums the declared per-agent USD cost estimates against `MAX_RUN_COST_USD`
(default $2.00). Exits 0 if under budget, 1 if over — used as a hard gate
in `.github/workflows/orchestrator-daily.yml` so a single accidental run
can never burn through more than the configured cap.

Estimates are *declared* per agent in `AGENT_COST_ESTIMATES_USD` below.
Update them when:
- An agent gains a new external paid dependency (API tier, LLM call, GPU).
- An agent changes scale (more matches, more iterations).
- A pricing change happens upstream.

Today every agent runs against free / open-data sources, so the totals
are $0.00. The gate exists so we cannot quietly drift past the budget
when that changes.

Usage:
    python3 tools/estimate_run_cost.py
    MAX_RUN_COST_USD=5 python3 tools/estimate_run_cost.py   # raise cap
    AGENT_COST_OVERRIDES='{"modeling": 1.50}' python3 ...   # one-off override

The script writes a Markdown summary to `$GITHUB_STEP_SUMMARY` when run
inside GitHub Actions so the cost breakdown shows up directly on the run
page.
"""

from __future__ import annotations

import json
import os
import sys

# Per-agent declared maximum cost per run, in USD. Keep aligned with the
# 8 functional agents in `docs/agents/0[1-8]-*.md`.
AGENT_COST_ESTIMATES_USD: dict[str, float] = {
    "data-engineering":     0.00,  # free APIs (martj42, StatsBomb, Understat, Wikipedia, Kalshi, Polymarket, OddsAPI free tier)
    "data-coverage":        0.00,  # local read-only audit
    "data-cleaning":        0.00,  # local pandas / pyarrow
    "market-normalization": 0.00,  # local devig
    "modeling":             0.00,  # local Dixon-Coles fits + 10k Monte Carlo on CPU
    "validation":           0.00,  # local schema + backtest
    "edge-comparison":      0.00,  # local join
    "orchestration":        0.00,  # glue only
}

DEFAULT_MAX_COST_USD = 2.00


def load_overrides() -> dict[str, float]:
    raw = os.environ.get("AGENT_COST_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("AGENT_COST_OVERRIDES must be a JSON object")
        return {str(k): float(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"ERROR: invalid AGENT_COST_OVERRIDES — {exc}", file=sys.stderr)
        sys.exit(2)


def estimate() -> tuple[dict[str, float], float, float]:
    """Return (per_agent_dict, total_usd, max_usd)."""
    estimates = dict(AGENT_COST_ESTIMATES_USD)
    overrides = load_overrides()
    for agent_id, cost in overrides.items():
        if agent_id not in estimates:
            print(f"ERROR: unknown agent '{agent_id}' in AGENT_COST_OVERRIDES", file=sys.stderr)
            sys.exit(2)
        estimates[agent_id] = cost

    total = round(sum(estimates.values()), 4)
    max_usd = float(os.environ.get("MAX_RUN_COST_USD", DEFAULT_MAX_COST_USD))
    return estimates, total, max_usd


def render_table(estimates: dict[str, float], total: float, max_usd: float, status: str) -> str:
    lines = [
        "| Agent | Estimated cost (USD) |",
        "|---|---:|",
    ]
    for agent_id, cost in estimates.items():
        lines.append(f"| `{agent_id}` | ${cost:.2f} |")
    lines.append(f"| **Total** | **${total:.2f}** |")
    lines.append(f"| **Cap (`MAX_RUN_COST_USD`)** | **${max_usd:.2f}** |")
    lines.append(f"| **Status** | **{status}** |")
    return "\n".join(lines)


def main() -> int:
    estimates, total, max_usd = estimate()
    over = total > max_usd
    status = "BLOCKED — over budget" if over else "OK"

    print(f"Pre-flight cost gate (cap ${max_usd:.2f}/run)")
    print("-" * 48)
    for agent_id, cost in estimates.items():
        print(f"  {agent_id:22s} ${cost:.2f}")
    print("-" * 48)
    print(f"  {'TOTAL':22s} ${total:.2f}")
    print(f"  {'STATUS':22s} {status}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## Pre-flight cost gate\n\n")
            fh.write(render_table(estimates, total, max_usd, status))
            fh.write("\n")

    if over:
        print(
            f"\nERROR: estimated total ${total:.2f} exceeds cap ${max_usd:.2f}.\n"
            "Lower an agent's estimate, raise MAX_RUN_COST_USD intentionally, "
            "or remove the offending agent from this run.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
