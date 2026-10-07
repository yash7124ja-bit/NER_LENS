# NER-LENS: Decision Support System for Road Corridor Risk Assessment

## Project Overview

NER-LENS is a decision-support system designed to assess risk in road corridors by combining heterogeneous evidence from multiple sources (e.g., weather, traffic, incident reports) into a normalized workflow. The system provides risk-oriented decision support while deferring official road-status decisions to authorized human authorities.

## Architecture

The system follows a modular pipeline:

1. **Evidence Ingestion** – Collects raw data from configured sources (SACHET, IMD, GSI, CWC).
2. **Evidence Normalization** – Transforms diverse inputs into a common internal format.
3. **Critical Evidence Validation** – Checks for missing, stale, or invalid evidence.
4. **Risk Assessment** – Evaluates risk using a deterministic, explainable rule engine.
5. **Decision Support** – Outputs risk state, probability-weighted minutes, and explanation for routing decisions.

## Current Risk Engine

The **active operational risk-assessment mechanism** is a deterministic and explainable rule engine. It operates as follows:

- If any route segment has status `"closed"` or `"restricted"` → `risk = high`, `probability = 0.8`
- Otherwise → `risk = low`, `probability = 0.2`

The system calculates:
```
probability_weighted_minutes = probability × 360
```

These values are **heuristic rule weights** used for decision support and are **not** statistically validated probabilities.

## Abstention

When critical evidence is missing, unknown, or otherwise insufficient:
- `state = insufficient_evidence`
- `source = abstention`

The system does **not** silently treat missing evidence as safe (zero risk). Abstention ensures that unavailable information does not lead to overconfident risk assessments.

## Laya Integration

NER-LENS includes an optional integration layer for the **Laya AI reasoning model** (`convaiinnovations/laya` from Hugging Face). This integration:

- Has been implemented and verified to load the model successfully.
- Can perform live inference in isolation (as demonstrated in testing).
- Is **not** the active provider for this delivery due to unresolved tokenizer compatibility in the standard Hugging Face loading path (worked via Laya's native API).
- Remains available as a future AI reasoning layer that can be activated without changing the upstream evidence and routing pipeline.

## Safety

- No silent zero-fill on missing evidence → abstention triggered instead.
- The system does **not** independently declare official road status (open/closed/safe/unsafe).
- No fabricated accuracy metrics or model performance claims are made.

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd D:\devlopment.sih

# Create and activate a virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -e .
```

## Configuration

Configure the system via environment variables or a `.env` file (see `.env.example` for template):

- `USE_MOCK_FALLBACK=true` – Enable mock fallback for data sources when live APIs fail.
- `DATA_SOURCE_PRIORITY` – Order of source attempts (e.g., `SACHET,IMD,GSI,CWC`).
- Other source-specific settings (e.g., API timeouts, retry counts).

## Running

Start the backend API server:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Testing

Run the test suite:

```bash
pytest
```

## Further Information

See `docs/CURRENT_STATUS.md` for a detailed status of implemented components.
See `docs/LEADER_HANDOFF.md` for a concise executive summary.
See `docs/FINAL_VERIFICATION.md` for verification records.