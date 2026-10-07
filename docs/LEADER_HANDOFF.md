# NER-LENS Leader Handoff

## Executive Summary

NER-LENS now has a working evidence-to-risk decision-support pipeline using the Laya AI reasoning model (`convaiinnovations/laya`) via the Laya package's native API. The system safely handles missing evidence via abstention and provides transparent, model-based risk scores for routing decisions.

## What Was Implemented

* evidence ingestion from multiple sources (SACHET, IMD, GSI, CWC)
* evidence normalization to a common internal format
* critical evidence validation with explicit abstention on missing/invalid data
* Laya-based risk assessment using the native Laya API (`agent.predict`)
* routing integration that consumes risk scores for route comparisons
* safety constraints preventing unsafe route recommendations

## Current Operational State

The **Laya model** (`convaiinnovations/laya`) accessed through the Laya package's native API (`laya.load` with `subfolder="typed-decisions"` and `fast=False`) is the active risk-assessment mechanism for this delivery. It returns:
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

* **missing evidence → abstention**: No silent zero-fill; insufficient evidence triggers `state = insufficient_evidence`, `source = abstention`.
* **no independent road-status declaration**: NER-LENS only provides decision support; official road status remains with authorized human authorities.
* **no fabricated accuracy metrics**: Model outputs are presented as they are, with confidence scores provided by the model.
* **transparent logic**: While the model is not a simple rule, its outputs are logged and explainable via the returned explanation.

## Known Limitations

* External data availability depends on source/API access
* The model's predictions are not calibrated to domain-specific statistical validation (though confidence scores are provided)
* The model requires the Laya package's native API; standard Hugging Face `AutoTokenizer`/`AutoModel` loading fails due to missing tokenizer assets in the `typed-decisions` subfolder.

## Next Possible Improvements

* Add domain-specific validation dataset to calibrate or benchmark the Laya model.
* Improve error handling and logging for Laya inference failures.
* Integrate additional verified real-time data sources as they become accessible.
* Consider optimizing model warm-up and inference latency for production use.