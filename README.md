# fulbol-mundial-26

A DuckDB-native probability model that predicts every match of the 2026 FIFA World Cup.

**[View the live prediction report](https://lnoguera171.github.io/fulbol-mundial-26/)** — methodology, 48-team probabilities, predicted bracket.

## What this is

`fulbol-mundial-26` builds a single model — `wc2026-predictor` — that reads only from the `curated.*` namespace of `data/wc2026.duckdb` and emits group-stage 1X2 probabilities plus a 10k-iteration Monte Carlo bracket simulation. The model is a Poisson-with-luck goals model with a tournament Monte Carlo wrapper.

The repo started as a multi-contributor model-comparison workbench. That framing has been pared down: there is one active model today, and the contribution surface is shaped around extending it (or adding a parallel model under the same `methodology/` convention). The full as-is structure — directory map, data flow, dormant code scheduled for deletion — lives in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## How to run

```bash
# 1. Build the analytics DB end-to-end (~10s)
python3 tools/build_duckdb.py

# 2. Verify it (sanity assertions; exit 0 = healthy)
python3 tools/verify_duckdb.py

# 3. Run the canonical model — group-stage 1X2 probabilities
python3 methodology/wc2026-predictor/model.py

# 4. Run the tournament Monte Carlo (10k iters, seed=42 by default)
python3 methodology/wc2026-predictor/simulate.py
```

Steps 3 and 4 write to `results/wc2026-predictor/<today>/`.

## Models in the repo

| Model | Folder | Approach | Status |
|---|---|---|---|
| `wc2026-predictor` | `methodology/wc2026-predictor/` | DuckDB-native Poisson with per-game luck factor + Monte Carlo bracket | active |

## Contributing a new model

Copy `methodology/_template/` as your starting point and read [`db/SCHEMA.md`](./db/SCHEMA.md) for the curated-layer read contract. Model guardrails (reproducibility, subjectivity policy, validation bar) are in [`DEVELOPMENT.md`](./DEVELOPMENT.md#model-guardrails).

## Where to read more

| What | Where |
|---|---|
| As-is structure + tech stack + data flow | [`ARCHITECTURE.md`](./ARCHITECTURE.md) |
| Contribution workflow + model guardrails | [`DEVELOPMENT.md`](./DEVELOPMENT.md) |
| Agent catalog (5 active roles) | [`AGENTS.md`](./AGENTS.md) |
| DuckDB schema contract | [`db/SCHEMA.md`](./db/SCHEMA.md) |
