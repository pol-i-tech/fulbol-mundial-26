## What does this PR do?

<!-- One sentence: new model, data pipeline update, bug fix, etc. -->

## Type of change

- [ ] New prediction model (`results/<model-name>/`)
- [ ] Data pipeline change (`tools/`)
- [ ] Model update / recalibration
- [ ] Documentation
- [ ] Bug fix

---

## Model checklist (required for any new or updated model)

### Reproducibility
- [ ] `methodology/<model-name>/` exists with runnable code or notebook
- [ ] `methodology/<model-name>/README.md` documents the exact command to reproduce predictions
- [ ] All input data comes from `data/derived/` or documented public sources — no manual data entry
- [ ] Random seeds are set explicitly (results are deterministic)

### Model card
- [ ] `results/<model-name>/MODEL.md` is filled in: approach, data sources, training window, calibration method, confidence convention, known limitations
- [ ] **"Subjective adjustments" section** is present — every manually set parameter is listed with its value and justification
- [ ] Backtest results reported: log-loss, Brier score, accuracy vs at least one tournament (WC2022 / Euro2024 / Copa2024)
- [ ] Validation is walk-forward only (no in-sample testing)

### Prediction file
- [ ] Predictions at `results/<model-name>/<YYYY-MM-DD>/predictions.csv` with all 8 required columns
- [ ] Probabilities sum to ~1.0 per `(match_id, market_type)` for mutually exclusive markets
- [ ] All team codes are 3-letter FIFA format (ARG, FRA, MEX…)
- [ ] `notes` field contains model reasoning only — no market comparisons or edge flags

## Data pipeline checklist (required for any `tools/` change)

- [ ] New raw data written to `data/raw/<source>/<YYYY-MM-DD>/` (immutable, date-stamped)
- [ ] Derived outputs written to `data/derived/` as `.parquet`
- [ ] Script is idempotent: safe to re-run without duplicating data
- [ ] No hardcoded credentials or API keys in code

## Reviewer notes

<!-- Anything the reviewer should pay special attention to, especially any subjective adjustments -->
