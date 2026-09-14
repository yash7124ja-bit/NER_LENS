# Offline evaluation

Install `uv sync --extra evaluation` for logistic regression. The rainfall and prevalence baselines use only the Python standard library.

```
uv run python -m ner_lens.evaluation data/verified-outcomes.csv --cutoff 2026-01-01T00:00:00Z --output data/model-card.json
```

This fails closed if the input is missing, has no verified outcomes, contains synthetic rows without an explicit flag, lacks three annual cohorts, or leaks future features or outcome labels across folds. No real dataset ships with this implementation. Actual NER LENS performance remains **not measured** until independently reviewed evidence is supplied. A CSV asserting `verified` is not proof: evidence references, reviewer identity, coverage and event grouping require independent review.

Required CSV columns:

- `event_id`, `segment_id`, `label`, `verification_status`, `evidence_ref`, `reviewer`
- `season` (annual monsoon cohort year), `road_band`, `event_type`, `rainfall_mm`, `synthetic` (`true` or `false`)
- `issued_at`, `occurred_at`, `published_at`, `retrieved_at`, `verified_at`
- `feature_observed_at`, `feature_published_at`, `feature_retrieved_at`

All timestamps require time zones. Outcomes must occur strictly after issue time and within six hours; label publication, retrieval and verification follow occurrence. Labels must be verified by the supplied cutoff. Feature publication and retrieval must precede or equal issue time. Rainfall must be finite, nonnegative or empty; empty values remain missing. Labels are `disrupted`, `not_disrupted_observed`, `unknown` or `ambiguous`. Blank, unknown, ambiguous and unverified labels are counted and excluded, never converted to negatives. Verified passability requires positive evidence, not absence of disruption reports. Duplicate segment/issue observations fail.

The latest annual cohort is test, the preceding cohort calibration, and all earlier cohorts training. Event groups cannot cross folds. Earlier labels must be verified before the next fold begins, and six-hour horizons cannot overlap the next fold. The curator must confirm complete monsoon coverage, consistent units/rainfall window, source licensing, geometry association, vehicle scope and grouping of nearby observations. The simplified CSV does not establish those facts automatically.

The training-band prevalence baseline falls back to training global prevalence for unseen bands. The prespecified rainfall rule uses 100 mm and abstains for missing rain, source age over 24 hours or unseen road bands. This rainfall-only rule is **not** the full susceptibility-aware operational Baseline B. Optional regularized logistic regression standardizes training features (rainfall, missing indicator, source age), then fits sigmoid calibration on the calibration cohort. Zero in the logistic feature matrix is accompanied by a missing indicator; inference still abstains on missing rain. Hyperparameters and threshold are fixed before test evaluation.

The JSON card includes SHA-256 of the exact CSV, training verification cutoff, fold counts, exclusions, configuration, standardized coefficients, test prevalence, average precision (stepwise PR-AUC; ties grouped), Brier score, five reliability bins, and 95% percentile bootstrap intervals sampled by event group. Slices cover year, event type, road band and freshness. Abstentions and coverage are reported; metrics use only non-abstaining predictions, so comparisons must account for different coverage. Empty-positive slices have undefined AP (`null`); intervals with fewer than two groups are undefined. Small counts can yield unstable or degenerate intervals. Synthetic fixtures exercise the code only.

Every card sets `approved_for_operations: false`. Status is `TEST_ONLY_SYNTHETIC` when any included row is synthetic, otherwise `UNAPPROVED_RETROSPECTIVE_EVALUATION`. Set `EVALUATION_MODEL_CARD` to this output path for API display; display is not promotion. No model registry or operational state changes occur. Independent geographic holdout, source-removal sensitivity, owner-approved recall/false-alert limits, full Baseline B comparison and sufficient positive event groups remain required before approval. Never select a model by repeated runs against the final test cohort.

Run executable validation:

```
uv run pytest tests/test_evaluation.py -q
```

Tests construct temporary, unmistakably synthetic CSV files and cover known metric values, tied ranking, temporal leakage, event overlap, missing labels/rainfall, optional logistic fitting, reproducibility and a CLI run that refuses synthetic input by default.
