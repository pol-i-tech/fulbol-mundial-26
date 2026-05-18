# Refinement Loop

This is the protocol that turns "constantly refining models" into a sequence of audited, walk-forward steps. It exists because the project's `DEVELOPMENT.md` Subjectivity and bias policy is the strongest constraint on any "refining" role — a parameter change without held-out evidence is post-hoc fitting, and that's exactly what this protocol prevents.

**Authoritative source:** [`DEVELOPMENT.md` — Subjectivity and bias policy](../../DEVELOPMENT.md#subjectivity-and-bias-policy). This protocol does not relax that policy. It operationalizes it.

Every Modeling role spec links here as their refinement contract.

## When to use

Use this protocol whenever a Modeling role wants to:

- Change a model parameter (decay rate, importance weight, prior, blending coefficient)
- Add a new feature (new data layer, new signal, new market type)
- Add or remove a subjective adjustment (team tier, confederation bonus, draw cap)
- Re-fit on an expanded data window
- Wire in a previously-unwired data source (e.g. `squad_xg_ratings.parquet` into the compound model)

If you are *not* changing the model — just producing a new dated snapshot with the existing methodology — you do not need this protocol. Run the model, validate, commit.

## The protocol

### 1. Hypothesis

State the hypothesis in one or two sentences before writing code. Write it in the PR description and in the eventual `methodology/<model>/CHANGELOG.md` entry.

Examples:

- "Adding the `squad_xg_ratings` blended xG/90 as an attack covariate will improve xG-Poisson log-loss on Euro2024 by ≥ 0.02."
- "Reducing the time-decay xi from 0.0025 to 0.0015 will close the gap to Pinnacle log-loss on the WC2022 holdout."

A hypothesis names: the change, the metric, the held-out tournament, and the expected direction.

### 2. Branch

`git checkout -b <your-name>/<model>-<short-description>` per `DEVELOPMENT.md`. The branch name must say which model is being touched.

### 3. Snapshot the baseline

Before the change, regenerate the current model's predictions and validation metrics:

```bash
python3 methodology/<model>/<model>.py
python3 tools/validate_predictions.py results/<model>/<date>/predictions.csv
python3 wc2022_xg_backtest.py   # or the model's own backtest
```

Record the current `log-loss`, `Brier`, `accuracy`, and `ECE` (when available) under "Baseline" in your CHANGELOG entry. **Do not skip this.** Without a baseline, "improvement" is unmeasurable.

### 4. Make the change

Modify only the methodology code and the parameter you named in the hypothesis. **No drive-by changes.** A drive-by change invalidates the comparison.

If the change adds a parameter to "Subjective adjustments," update `MODEL.md` *in the same commit* as the code change.

### 5. Walk-forward backtest on a held-out tournament

This is the rule that prevents post-hoc fitting:

> **You may not backtest on the same tournament whose results motivated the change.**

If your hypothesis came from observing WC2022 results, validate on Euro2024 or Copa2024. If it came from Euro2024, validate on WC2022.

Walk-forward only — no in-sample validation. The training window must end before the held-out tournament starts.

```bash
python3 wc2022_xg_backtest.py     # if Euro2024 motivated the change
# OR (when supported)
python3 tools/backtest_euro2024.py
python3 tools/backtest_copa2024.py
```

### 6. Calibration check

For models claiming edge against markets, generate a calibration plot or compute ECE. The plot lives at `results/<model>/calibration/<date>.png` (gitignored if large) and the ECE value goes in the CHANGELOG entry.

A change that improves accuracy but worsens calibration is **not** an improvement for betting. Calibration governs.

### 7. Compare against stop-conditions

Roll back the change if **any** of these hold:

| Stop-condition | What it means |
|---|---|
| `validate_predictions.py` fails | Schema or sum-to-one violation; never reaches the backtest |
| Log-loss regresses by > 0.01 vs the prior `model_version` | The change is worse than what was already shipped |
| ECE worsens beyond noise | Calibration regression; not safe for edge calculation |
| Held-out accuracy is unchanged AND the change is a parameter "tuning" (not a new feature) | Null result; do not adopt fitting noise |

A null result on a *new feature* is acceptable to ship if it adds explanatory power for a documented blind spot — but say so explicitly in the CHANGELOG.

### 8. Update `methodology/<model>/CHANGELOG.md`

Append a row using the columns defined in the [template](../../methodology/_template/CHANGELOG.md). Required fields:

- date (ISO)
- `model_version` (semver bump or git SHA)
- change (one sentence)
- held-out evidence (tournament + metric delta)
- reviewer (whoever approves the PR)

If `methodology/<model>/CHANGELOG.md` doesn't exist yet, copy `methodology/_template/CHANGELOG.md` into the model's folder *in this PR*.

### 9. Update `MODEL.md`

If a "Subjective adjustments" parameter was added/changed/removed, the table in `MODEL.md` must reflect it. Reviewers verify the table matches the code.

### 10. Open the PR

PR description must include:

- The hypothesis (verbatim from step 1)
- Baseline metrics
- New metrics (held-out tournament, log-loss, Brier, accuracy, ECE)
- Decision: ADOPT / ROLL BACK / ADOPT WITH CAVEAT (with caveat text)
- Link to the CHANGELOG entry

The Review role rejects any refinement PR missing any of the above, citing this protocol.

## What the Review role checks

The [Review role spec](quality-review.md) lists these as required checks for any PR labeled `refinement` or any PR touching `methodology/<model>/`:

1. Hypothesis is present and specific.
2. Baseline metrics are recorded.
3. Held-out tournament is **not** the tournament cited in the hypothesis.
4. CHANGELOG entry exists and matches the code change.
5. `MODEL.md` "Subjective adjustments" table is consistent with the code.
6. `tools/validate_predictions.py --all` passes.
7. No drive-by changes outside the model's `methodology/<model>/` and `results/<model>/` trees.

If any of (3) or (4) fails, the PR is closed without merge — these are hard rules from the subjectivity policy.

## What this protocol does *not* cover

- Adding a new model from scratch — see [`DEVELOPMENT.md` — Adding a New Model](../../DEVELOPMENT.md#adding-a-new-model).
- Producing a fresh dated snapshot with no methodology change — that is a regular re-run of the model against the latest curated layer (manual today; an automated cadence is sketched in [`../ideation/2026-05-15-role-08-orchestration.md`](../ideation/2026-05-15-role-08-orchestration.md)).
- Adding a new data layer that does not yet feed any model — that is acquisition work, owned by an Acquisition role.
