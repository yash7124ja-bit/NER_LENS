# Hackathon Replay Implementation Track

**Decision date:** 2026-09-10  
**Decision owner:** Hill Patel  
**Time box:** submission build within 10 hours

## Decision

Implementation may proceed before the overall Terra P0 human/partner gate is closed, but only as a **replay-only hackathon prototype**.

This decision does not change the M0 evidence findings and does not authorize claims of live road status, present passability, legal or structural clearance, production readiness, field validation, or predictive-model accuracy.

## Mandatory runtime behavior

- Unresolved policy ownership, critical-source freshness, or ground-truth coverage produces `insufficient_evidence`.
- `insufficient_evidence` never contains a recommended route.
- Only an authorized, audited status decision may change operational status.
- Weather, hazard, model, synthetic, fixture, and replay data cannot close or reopen a road.
- All bundled demonstration records are visibly labelled `replay` or `synthetic`.
- The real GraphHopper evidence establishes graph representability only.
- APIs and documentation must expose evidence timestamps, provenance, graph version, policy version, and limitations.

## Build priority

1. Bootable API and deterministic replay.
2. Corridor state, evidence review, status decision, route comparison, and audit trail.
3. Mission/report flow needed for the demonstration.
4. Security, validation, OpenAPI, tests, and reproducible local startup.
5. Only then: optional integrations that can be completed and verified honestly.

## Deferred gates

Live source ingestion, live operational recommendations, model promotion, production release, and field deployment remain blocked by the unresolved items in `m0-evidence-checkpoint.md`.

