"""Tiny client for posting agent state to the local Miniverse server.

Miniverse runs the visual world at http://localhost:5173 and accepts heartbeats
on http://localhost:4321/api/heartbeat. Drop these calls into long-running
scripts (pulls, backtests, simulations) so the citizen for that agent reflects
real work.

Example:
    from tools.miniverse_heartbeat import heartbeat
    heartbeat("poisson", state="working", task="WC2022 backtest")
    ...
    heartbeat("poisson", state="idle", task=None)

If the Miniverse server isn't running, calls silently no-op so production runs
are never blocked by visualization.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_DEFAULT_URL = os.environ.get("MINIVERSE_URL", "http://localhost:4321")
_VALID_STATES = {"working", "idle", "thinking", "sleeping", "error", "speaking"}

# The 8 functional agents. Keys are the heartbeat IDs that the pipeline scripts
# pass to `heartbeat(agent=...)`; values are the display names that show up in
# the Miniverse UI. Keep aligned with `docs/agents/0[1-8]-*.md`.
AGENTS: dict[str, str] = {
    "data-engineering": "Data Engineering",
    "data-coverage": "Data Coverage",
    "data-cleaning": "Data Cleaning + FE",
    "market-normalization": "Market Normalization",
    "modeling": "Modeling / Data Science",
    "validation": "Backtest / Validation",
    "edge-comparison": "Edge / Comparison",
    "orchestration": "Orchestration",
}


def register_all(base_url: str = _DEFAULT_URL, timeout: float = 0.5) -> dict[str, bool]:
    """Send an idle heartbeat for every agent in `AGENTS`. Useful at process
    start so the world has all 8 citizens before any work begins."""
    return {
        agent_id: heartbeat(
            agent_id, state="idle", task=None, name=display, base_url=base_url, timeout=timeout
        )
        for agent_id, display in AGENTS.items()
    }


def heartbeat(
    agent: str,
    *,
    state: str = "working",
    task: str | None = None,
    name: str | None = None,
    energy: float | None = None,
    base_url: str = _DEFAULT_URL,
    timeout: float = 0.5,
) -> bool:
    """POST a heartbeat for `agent`. Returns True if accepted, False on any failure."""
    if state not in _VALID_STATES:
        raise ValueError(f"state must be one of {sorted(_VALID_STATES)}")

    payload: dict = {"agent": agent, "state": state, "task": task}
    if name is not None:
        payload["name"] = name
    if energy is not None:
        payload["energy"] = energy

    req = urllib.request.Request(
        f"{base_url}/api/heartbeat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if not args:
        print(
            "Usage:\n"
            "  miniverse_heartbeat.py register-all\n"
            "  miniverse_heartbeat.py <agent> [state] [task]\n\n"
            f"Known agents: {', '.join(AGENTS)}"
        )
        sys.exit(2)
    if args[0] == "register-all":
        results = register_all()
        for agent_id, ok in results.items():
            print(f"  {agent_id:22s} {'ok' if ok else 'unreachable'}")
        sys.exit(0 if all(results.values()) else 1)
    agent = args[0]
    state = args[1] if len(args) > 1 else "working"
    task = args[2] if len(args) > 2 else None
    name = AGENTS.get(agent)
    ok = heartbeat(agent, state=state, task=task, name=name)
    print("ok" if ok else "miniverse server unreachable")
