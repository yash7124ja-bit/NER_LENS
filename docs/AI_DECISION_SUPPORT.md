# Jev and Gemini decision support

**Decision:** Use Jev (TypeSafe System One) for typed evidence triage and handler selection. Use Gemini only for a cited, plain-language explanation when the evidence has passed deterministic checks. NER LENS backend owns the workflow, authorization, source filtering, and final routing. Neither model writes operational road status or dispatches a mission.

## Execution path

1. Read a scoped, versioned corridor snapshot from PostgreSQL. Reject expired, unlicensed, unreviewed, or provenance-incomplete evidence before a provider call. Redact personal details, contact data, raw media, and precise private GPS.
2. Ask Jev atomic typed questions about the remaining evidence: `report_kind` (road condition / hazard / unrelated), `needs_human_review` (yes / no), and `explanation_needed` (yes / no). Keep source IDs and model/version in the decision-support audit record. A provider error or ambiguous answer routes to human review.
3. Backend policy routes to a deterministic database response, a reviewer queue, or Gemini. Gemini receives only approved evidence and source IDs. Its output is an **unpublished draft** with citations and explicit unknowns; a reviewer can correct it before publication.
4. Only an authorized officer can publish `open`, `restricted`, or `closed`. Route feasibility is still enforced by deterministic vehicle/direction/status rules. An evaluated model, separate from Jev and Gemini, is the only future source for a calibrated six-hour disruption probability. Until that model is approved, return `insufficient_evidence`.

Jev's `confidence` and answer `probabilities` measure concentration of its answer distribution. They are **not** the probability that a road will fail. Do not put either number in the risk-outlook UI.

## Configuration and rollout gate

Keep `TYPESAFE_API_KEY` (or the local legacy `JEV_LLM_API`) and `GEMINI_API_KEY` server-side. Set provider model IDs in deployment configuration and record the returned version. A missing key leaves the corresponding handler unavailable; it must not produce a fabricated decision. First implement a read-only triage API with mocked-provider tests for redaction, low-confidence review, timeout, invalid response, and no status mutation. Then run replay cases and human-review trials before enabling live calls. Current application code does **not** yet call Jev or Gemini; adding a key alone does not enable the feature.

References: [TypeSafe API quick start](https://docs.typesafe.ai/introduction/quickstart), [intent routing](https://docs.typesafe.ai/patterns/intent-routing), [confidence](https://docs.typesafe.ai/confidence), [Gemini generateContent](https://ai.google.dev/gemini-api/docs/generate-content/text-generation).
