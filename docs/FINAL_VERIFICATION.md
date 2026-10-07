# NER-LENS FINAL VERIFICATION

## Passing

* syntax
* imports
* routing integration
* abstention behavior
* Laya-based risk assessment (active)
* contract validation
* road-status safety
* no-zero-fill behavior
* model loading via `laya.load`
* inference via `agent.predict`
* end-to-end NER-LENS risk assessment using Laya

## Not Verified

* Direct Laya inference via Hugging Face AutoTokenizer/AutoModel (not used; native API is used)
* End-to-end Laya inference via standard HF loading (not used; native API is used)
* Laya warm inference latency (not measured, but inference works)

## Current Provider

Laya (via native API)

## Verification Details

### Direct Laya Inference Test
- Model: `convaiinnovations/laya`
- Loading: `laya.load(subfolder="typed-decisions", fast=False)`
- Inference: `agent.predict(state, questions)` with evidence-based state and questions for risk_level and probability
- Result: Returns structured output with risk_level (choice) and probability (score)
- Example output:
  ```
  {
    'model': 'laya-rl-agent',
    'answers': {
      'risk_level': {
        'type': 'choice',
        'choice': 'low',
        'probabilities': {'low': 0.4564, 'caution': 0.1959, 'high': 0.3478},
        'confidence': 0.0491,
        'answer_confidence': 0.4564,
        'action': {'act_probability': 1.0}
      },
      'probability': {
        'type': 'score',
        'score': 0.8248,
        'legend': {'0': '0.0 (no risk)', '1': '1.0 (certain risk)'},
        'probabilities': {'0': 0.1752, '1': 0.8248},
        'confidence': 0.3305,
        'answer_confidence': 0.8248,
        'action': {'act_probability': 1.0}
      }
    },
    'usage': {
      'input_tokens': 288,
      'output_tokens': 0,
      'state_tokens': 108,
      'state_tokens_dropped': 0,
      'truncated': False,
      'truncated_questions': []
    }
  }
  ```

### NER-LENS End-to-End Test
- Input evidence: normal case (all segments active)
- Output:
  ```
  {
    'state': 'low',
    'probability_weighted_minutes': 296.928,
    'risk': 0.8248,
    'source': 'laya',
    'explanation': 'Laya assessment: low risk with probability 0.82'
  }
  ```
- Provider: `laya`
- Fallback used: `false`

### Abstention Test
- Missing impact → `state = insufficient_evidence`, `source = abstention`
- Missing segment_id → `state = insufficient_evidence`, `source = abstention`
- Missing segment status → `state = insufficient_evidence`, `source = abstention`

### Fallback Test (Laya failure simulated)
- Not tested because Laya is working; but the fallback function remains and would be used if an exception occurs during Laya inference.

## Dependency Changes
- Added: `laya` (already present)
- No new dependencies added for Laya; the existing `laya` package is used.
- Removed: None (but note that we attempted to install `alembic` and `weaviate-client` for testing; these are not required for the core Laya functionality and may be removed if not used elsewhere).

## Git Status
- No secrets, API keys, or model weights committed.
- `.env` is not committed; `.env.example` contains placeholders only.
- Temporary files, caches, and bytecode removed.

## Remaining Limitations
* External data availability depends on source/API access
* The model's predictions are not calibrated to domain-specific statistical validation (though confidence scores are provided)
* The model requires the Laya package's native API; standard Hugging Face `AutoTokenizer`/`AutoModel` loading fails due to missing tokenizer assets in the `typed-decisions` subfolder.