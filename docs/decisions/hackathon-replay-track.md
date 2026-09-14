# Hackathon Replay Implementation Track

**Decision date:** 2026-09-10  
**Decision owner:** Hill Patel  
**Time box:** 2026-09-10 13:06–23:06 IST

## Decision

Implementation may proceed before the overall Terra P0 human/partner gate is closed, but only as a **replay-only hackathon prototype**.

This record explicitly supersedes the runtime-start prohibition in `m0-evidence-checkpoint.md`, `MILESTONES.md`, `VALIDATION_PLAN.md`, and `ORCHESTRATION.md` only for tasks `A-M1-01`, `A-M1-02`, `A-M1-03`, `B-M1-02`, `S-M1-01`, `A-M2-01`, `A-M2-02`, `B-M2-01`, and `S-M2-01` during the time box above. Terra P0 remains `BLOCKED`.

This decision does not change the M0 evidence findings and does not authorize claims of live road status, present passability, legal or structural clearance, production readiness, field validation, or predictive-model accuracy.

## Mandatory runtime behavior

- Unresolved policy ownership, critical-source freshness, or ground-truth coverage produces `insufficient_evidence`.
- `insufficient_evidence` never contains a recommended route.
- Only an authorized, audited status decision may change operational status.
- Weather, hazard, model, synthetic, fixture, and replay data cannot close or reopen a road.
- All bundled demonstration records are visibly labelled `replay` or `synthetic`.
- The real GraphHopper evidence establishes graph representability only.
- APIs and documentation must expose evidence timestamps, provenance, graph version, policy version, and limitations.
- Every demo-visible state, status, route, audit, and mission response contains `data_mode: "replay"`, provenance, and limitations.
- The only demo policy is `replay_unapproved_v1`; route mode is `insufficient_evidence` and `recommended_route_id` is always `null`. Test-only policies may exercise other contract outcomes but are not exposed by the demo API.
- Synthetic actor `replay_reviewer` may review evidence but cannot publish status. Synthetic actor `replay_district_officer` may publish replay status only inside synthetic jurisdiction `replay_guwahati_silchar`. These identities represent no real person, office, authority, or validation.
- No live source, field report, GPS input, public deployment, or operational dispatch is authorized by this exception.

## Build priority

1. Bootable API and deterministic replay.
2. Corridor state, evidence review, status decision, route comparison, and audit trail.
3. Mission/report flow needed for the demonstration.
4. Security, validation, OpenAPI, tests, and reproducible local startup.
5. Only then: optional integrations that can be completed and verified honestly.

## Deferred gates

Live source ingestion, live operational recommendations, model promotion, production release, and field deployment remain blocked by the unresolved items in `m0-evidence-checkpoint.md`.

## Continuation — 14 September 2026

The project owner's explicit continuation request on this date authorizes renewed
local implementation and integration across `NER_LENS` and `NER_LENS_FRONTEND`.
This supersedes the expired time box for that requested work, not the live/production
gates. The selected checkpoint completes S-M1-01's bootable schema/API shell and a
read-only client corridor flow, plus corrections to existing configuration and identity.
The original M0 findings and all mandatory replay safety behavior remain in force.
The initial frontend repository was empty; no prior frontend implementation was replaced.
