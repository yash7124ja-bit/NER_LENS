# Current Status

## Overall Status

NER-LENS currently operates using the Laya AI reasoning model (`convaiinnovations/laya`) via the Laya package's native API for risk assessment.

## Completed

* evidence ingestion architecture
* normalization
* critical evidence validation
* abstention
* Laya-based risk assessment (active)
* routing integration
* safety controls
* testing performed

## Active Risk Assessment

The active mechanism is the Laya model (`convaiinnovations/laya`) accessed through the Laya package's native API (`laya.load` with `subfolder="typed-decisions"` and `fast=False`). It returns:
- `state`: one of `insufficient_evidence`, `low`, `caution`, `high`
- `probability_weighted_minutes`: derived from predicted probability (0.0–1.0) × 360 minutes
- `risk`: the predicted probability value (0.0–1.0)
- `source`: `laya` (indicating live model inference)
- `explanation`: human-readable rationale for the risk level

## Laya Status

Laya integration is implemented and is the active operational mechanism for this delivery.
Live inference has been verified to work end-to-end.
The model loads successfully via `laya.load`.
Tokenizer compatibility was resolved by using the Laya package's native inference API (`agent.predict`) rather than the Hugging Face AutoTokenizer/AutoModel approach.

## Safety

* No silent zero-fill on missing evidence
* Abstention on insufficient evidence
* No official road-status declaration
* No fabricated model accuracy claims

## Data Source Status

Only real data, snapshots, and mock/fallback are used as appropriate.
API availability is not exaggerated; missing APIs trigger mock fallback.

## Known Limitations

* External data availability depends on source/API access
* The model's predictions are not calibrated to domain-specific statistical validation (though confidence scores are provided)