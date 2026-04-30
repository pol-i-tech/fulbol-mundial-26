# <model-name> — Methodology

## How to reproduce

```bash
# Install dependencies (if any beyond project base)
pip install -r methodology/<model-name>/requirements.txt

# Run the model — regenerates results/<model-name>/<today>/predictions.csv
python3 methodology/<model-name>/model.py
```

## Inputs

| File | Source | Description |
|---|---|---|
| `data/derived/...` | `tools/...` | ... |

## Outputs

`results/<model-name>/<YYYY-MM-DD>/predictions.csv` — 8-column predictions schema

## Subjective adjustments

List every manually set parameter here. This section is required.

| Parameter | Value | Justification / evidence |
|---|---|---|
| example: home advantage weight | +0.06 | Average home win rate uplift across 2018–2022 WC qualifying (n=312 matches) |

If this model has no subjective adjustments, state: "No subjective adjustments — all parameters derived from data."
