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

- [ ] `MODEL.md` filled in: approach, data sources, training window, calibration method, confidence convention, known limitations
- [ ] Predictions file at `results/<model-name>/<YYYY-MM-DD>/predictions.csv` with all 8 required columns
- [ ] Probabilities sum to ~1.0 per `(match_id, market_type)` for mutually exclusive markets
- [ ] Team codes use 3-letter FIFA format (ARG, FRA, MEX…)
- [ ] Model validated against at least one historical tournament (WC2022, Euro2024, or Copa2024)
- [ ] Backtest accuracy and log-loss reported in `MODEL.md`

## Data pipeline checklist (required for any `tools/` change)

- [ ] New raw data written to `data/raw/<source>/<YYYY-MM-DD>/` (immutable, date-stamped)
- [ ] Derived outputs written to `data/derived/` as `.parquet` (and `.csv` if human-readable)
- [ ] Script is idempotent: safe to re-run without duplicating data
- [ ] No hardcoded credentials or API keys in code

## Reviewer notes

<!-- Anything the reviewer should pay special attention to -->
