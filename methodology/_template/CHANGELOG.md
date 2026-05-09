# Changelog: <your-model-name>

> Append one row per refinement. Newest first. Do not edit historical rows.
>
> The [refinement-loop protocol](../../docs/agents/refinement-loop.md) requires every parameter or methodology change to land here with held-out evidence.

| Date | model_version | Change | Hypothesis | Held-out tournament | Metric delta (log-loss / Brier / accuracy / ECE) | Decision | Reviewer |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

## Decision values

- **ADOPT** — change is shipped; new `model_version` is now the current version
- **ROLL BACK** — change rejected; baseline is still current
- **ADOPT WITH CAVEAT** — shipped with a documented limitation; caveat text required in the row's Change column

## What does not go here

- Routine weekly snapshots (no methodology change) — those live in `results/<model>/<date>/`, not here.
- Bug fixes that do not change predictions — note in commit message, not here.
- Documentation-only changes to `MODEL.md` — note in commit message.

## What must go here

- Any change to a parameter listed in `MODEL.md` "Subjective adjustments"
- Any change to feature inputs, data window, or fitting method
- Any wiring-in of a previously-unused data source
- Any change that produces a different `predictions.csv` for the same input data
