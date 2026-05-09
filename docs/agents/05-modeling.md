# 05 · Modeling / Data Science Agent

> Function-first agent: **probabilities**. Reads `data/derived/`, fits statistical models, writes one prediction snapshot per match per model. Stateless with respect to markets — never sees Kalshi, Polymarket, or Pinnacle. The six `modeling-*.md` legacy specs are concrete model heads under this role.

## Mission

Produce calibrated probability estimates for every WC2026 match (1X2, outright, group winner, advance, totals, BTTS). The Modeling Agent owns six model heads — Elo baseline, Form-last-10, Poisson-goals, xG-Poisson, Ensemble, Compound-model — and ships exactly one `predictions.csv` per model per snapshot date. Models are intentionally separated by signal so the Ensemble can blend them, the Comparison Agent can flag agreement (Golden Zone), and the Validation Agent can backtest each one independently.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Squad xG ratings | `data/derived/squad_xg_ratings.parquet` | Blended national + club xG90. |
| Team attack ratings | `data/derived/team_attack_ratings.parquet` | Nation-level pressing/attack signal. |
| StatsBomb team xG | `data/derived/statsbomb_team_xg.parquet` | Drives xG-Poisson. |
| martj42 results | `data/raw/martj42/latest/results.csv` | Drives Elo, Form, Poisson-goals. |
| eloratings.net | external snapshot via `tools/pull_elo.py` (Data Engineering) | Long-term Elo prior. |
| Match importance weights | constants in `tools/weekly_pull.py` | For recency-decayed fits. |

## Outputs

| Output | Path | Schema |
|---|---|---|
| Per-model predictions | `results/<model-name>/<YYYY-MM-DD>/predictions.csv` | Canonical 8-column schema (see DEVELOPMENT.md) |
| Methodology docs | `methodology/<model-name>/` | `README.md`, `<model>.py`, `requirements.txt` |
| Model card | `results/<model-name>/MODEL.md` | Documents subjective adjustments + limitations |

The six current model heads:

- `elo-baseline` — long-term reputation prior, eloratings + decades of head-to-heads weighted by goal margin.
- `form-last-10` — average points/game across 10 competitive fixtures with importance weights.
- `poisson-goals` — Dixon-Coles on actual goals, exponential time decay (`xi ∈ [0.001, 0.003]`).
- `poisson-xg` — Dixon-Coles on StatsBomb xG.
- `ensemble-v2` / `ensemble-e3` — equal-weight blend (0.333/0.333/0.333) of Elo + Form + xG-Poisson; calibrated edge number (log-loss 1.054 on WC2022).
- `compound-model` — research blend with squad ratings, Bayesian Elo prior, 10k Monte Carlo bracket sim.

## Allowed write paths

- `methodology/<model-name>/**`
- `results/<model-name>/<YYYY-MM-DD>/predictions.csv`
- `results/<model-name>/MODEL.md`

Forbidden: `data/raw/**`, `data/derived/**`, `results/comparisons/**`, any other model's directory, devig logic.

## Cadence

- **Daily via Orchestrator**, after the Cleaning Agent and Market Normalization Agent are green.
- **Per refinement** when a methodology change is proposed — must come paired with a Backtest Agent verdict before merge.

## Guardrails

- See [DEVELOPMENT.md — Model Guardrails](../../DEVELOPMENT.md#model-guardrails) — required artifacts, reproducibility standard.
- See [DEVELOPMENT.md — Subjectivity and bias policy](../../DEVELOPMENT.md#subjectivity-and-bias-policy) — every manual parameter must live in `MODEL.md` under "Subjective adjustments".
- See [DEVELOPMENT.md — Statistical validation bar](../../DEVELOPMENT.md#statistical-validation-bar) — log-loss < 1.099, walk-forward only.
- See [`refinement-loop.md`](./refinement-loop.md) — how to change parameters without violating no-post-hoc-fitting.
- Probabilities for mutually exclusive outcomes sum to [0.99, 1.01] per `(match_id, market_type)`.
- 3-letter FIFA codes throughout — never free-form country names.
- `notes` describes model reasoning only; **never** market comparisons or edge flags.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| Backtest / Validation | `predictions.csv` for the snapshot date | Per snapshot, per PR |
| Edge / Comparison | All models' `predictions.csv` for the same date | Daily |
| Documentation / Learnings | `MODEL.md`, refinement notes | On methodology change |

## Escalation

- Stop and escalate if: a probability sum falls outside [0.99, 1.01].
- Stop and escalate if: any `p_model` is outside [0, 1].
- Stop and escalate if: a manual parameter changed between snapshots without a Backtest Agent verdict.
- Stop and escalate if: log-loss on the most recent held-out tournament falls below the prior champion's number.
- Stop and escalate if: input parquets show staleness flags from the Coverage Agent for >25% of squads.

## Verification

- `tools/validate_predictions.py results/<model>/<YYYY-MM-DD>/predictions.csv` exits 0.
- The `methodology/<model>/` folder is runnable from a clean clone and regenerates the snapshot deterministically.
- `MODEL.md`'s "Subjective adjustments" section is non-empty and matches the actual code.
- Backtest Agent's report exists for every methodology change.
