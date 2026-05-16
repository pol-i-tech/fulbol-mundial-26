# Acquisition: International Results (martj42)

## Mission

Maintain the canonical history of international football match results. This is the backbone training data for Elo, Form-last-10, and goals-Poisson — every modeling role except market-derived ones depends on it. The source ([`martj42/international_results`](https://github.com/martj42/international_results)) is updated within ~24h of each match by an external maintainer, so this role's job is *idempotent re-pull and integrity-check*, not scraping.

## Inputs

| Input | Path or URL | Notes |
|---|---|---|
| Upstream CSV | `https://raw.githubusercontent.com/martj42/international_results/master/results.csv` | Single CSV; ~50k rows; no auth |

Rate limit: GitHub raw is generous; one pull per Sunday is well under any limit.

## Outputs

| Output | Path | Schema |
|---|---|---|
| Dated raw snapshot | `data/raw/martj42/<YYYY-MM-DD>/results.csv` | Upstream CSV verbatim |
| `latest` symlink-style copy | `data/raw/martj42/latest/results.csv` | Identical to most recent dated snapshot |

## Allowed write paths

- `data/raw/martj42/<YYYY-MM-DD>/`
- `data/raw/martj42/latest/`
- `tools/weekly_pull.py` (the existing puller; modify only the martj42 section)

## Cadence

`weekly` — pulled by `tools/weekly_pull.py` as part of the Orchestrator's Sunday run. Manual `on-demand` re-pulls are fine for catch-up.

## Guardrails

- Raw snapshot immutability — see [DEVELOPMENT.md — Architecture/Data flow](../../DEVELOPMENT.md#data-flow). Never edit `data/raw/martj42/<date>/`.
- Idempotency — see [DEVELOPMENT.md — Track B](../../DEVELOPMENT.md#track-b--data-contributor). Re-running on the same date must produce identical output or no-op.

## Hand-offs

| Downstream role | Artifact | Frequency |
|---|---|---|
| [Modeling](05-modeling.md) | `data/raw/martj42/latest/results.csv` (after curation into `curated.fact_match_results`) | on snapshot |

## Escalation

- Stop and escalate if: row count drops > 1% week-over-week (suggests upstream truncation).
- Stop and escalate if: schema columns differ from prior snapshot (upstream change requires audit).
- Stop and escalate if: HTTP non-200 from raw.githubusercontent.com — do not silently skip; the weekly run should fail loudly.

## Verification

- `data/raw/martj42/<date>/results.csv` exists and has the expected columns (`date,home_team,away_team,home_score,away_score,tournament,city,country,neutral`).
- Row count > prior snapshot's row count (or equal, if no new internationals played).
- `data/raw/martj42/latest/results.csv` is byte-identical to the dated snapshot.
