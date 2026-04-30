"""
<model-name>

Reproduce predictions by running:
    python3 methodology/<model-name>/model.py

Writes to: results/<model-name>/<today>/predictions.csv
"""

import random
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date

# Set seeds for deterministic output
random.seed(42)
np.random.seed(42)

TODAY = date.today().isoformat()
OUT_DIR = Path(f"results/<model-name>/{TODAY}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Load inputs from data/derived/ — never from manual data entry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 2. Model logic
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 3. Write predictions
# ---------------------------------------------------------------------------
# Required columns: as_of_date, match_id, market_type, outcome,
#                   p_model, confidence, model_version, notes
# Probabilities must sum to ~1.0 per (match_id, market_type)
# notes = model reasoning only, never market comparisons or edge flags

rows = []  # append dicts here

df = pd.DataFrame(rows, columns=[
    "as_of_date", "match_id", "market_type", "outcome",
    "p_model", "confidence", "model_version", "notes"
])
df.to_csv(OUT_DIR / "predictions.csv", index=False)
print(f"Wrote {len(df)} rows to {OUT_DIR}/predictions.csv")
