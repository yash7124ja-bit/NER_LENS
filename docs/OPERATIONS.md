# Operational workflow

`src/ner_lens/operations.py` exposes `build_router(factory, current_actor)` and shares the existing SQLAlchemy Base and persisted authorization boundary. Migration `0006_operations` adds reports, append-only review/status records, mission assignments, raw GPS observations, idempotent response storage and explicit status authority grants.

## API

All POST operations require `Idempotency-Key` and return 201. An identical actor/path/key/body replays the stored response; changing the body returns 409. A client report ID is independently deduplicated. Authorization is rechecked before every replay. Field report POST also accepts `X-Ner-Lens-Actor` as an expected-session guard; mismatches return 403, and the header never supplies identity.

- `POST /v1/field-reports`: canonical CONTRACTS.md schema; `segment_id` is required. Timestamps must have a timezone; future observations and points outside the corridor are rejected. Receipt means accepted for review, not a status change.
- `GET /v1/field-reports?segment_id=…&limit=100`: own reports for reporters, scoped reports for reviewers. `reports` contains metadata, receipt, and latest review state.
- `POST /v1/reviews/{evidence_id}`: `action`, `note`, optional `merge_into_evidence_id`. Merge requires another accepted report on the same segment. Reviews append history.
- `POST /v1/status-decisions`: canonical status schema. Requires active jurisdiction-bound authority plus officer permission. Non-unknown decisions require accepted segment reports or an explicit authority-order reason. Predictions cannot be supplied as evidence.
- `GET /v1/status-decisions?segment_id=…&direction=both&vehicle_profile=all`: current applicable decision, evidence and freshness. Expiry yields unknown; older open decisions never reappear. General reads of a narrower direction/vehicle decision yield unknown with `scope_required`.
- `POST /v1/missions`: canonical mission schema plus `assigned_actor_ids` (active field reporters in the corridor jurisdiction). Graph version is pinned. Delivery window end must be after start and creation. Consent time cannot be future. Non-null route IDs are currently rejected until persisted route ownership binding is available.
- `GET /v1/missions?corridor_id=…`: creator dispatcher's or assigned reporter's scoped missions, latest 100.
- `GET /v1/missions/{id}`: creator dispatcher or assigned field reporter; includes last fix, raw flags, fix age, deadline state and explicit unavailable ETA.
- `POST /v1/missions/{id}/start`: creator dispatcher or assigned reporter; starts collection only with recorded consent before deadline. No request body required.
- `POST /v1/missions/{id}/complete`: creator dispatcher or assigned reporter; closes collection, records completion time and deadline outcome, and rejects subsequent new GPS batches. Replaying a previously accepted batch returns its original receipt.
- `POST /v1/missions/{id}/positions`: canonical batch schema, 1–500 unique sequences. Only assigned reporters may submit. Requires active mission. Preserves capture/receipt times; pre-start/future fixes are rejected. Mission/device/sequence duplicates are retained once; changed sequence payload returns 409 atomically. Impossible jumps are flagged and remain raw; observations are never interpolated.

`MissionAssignment` uses composite `(actor_id, mission_id)` primary keys. GPS checks this table directly rather than trusting caller-supplied scope.

Routing may call `effective_status(session, segment_id, at=None, direction='both', vehicle_profile='all')`. Output includes `status`, `freshness`, `evidence_ids`, and decision metadata when present. Callers must treat unknown, expired and scope-required outcomes as insufficient evidence.

## Verification

Run `NER_LENS_ENV_FILE='' uv run pytest tests/test_operations.py` (set the environment variable using shell syntax appropriate to your platform). Tests migrate a disposable SQLite database up and down and cover report replay/conflict, actor mismatch, all role and jurisdiction combinations for report creation, revoked authority, reviewed status publication/expiry, coordinate/time rejection, mission/GPS assignment, duplicate batches and impossible-jump preservation. These are synthetic test fixtures, not live corridor safety evidence.

## Remaining external boundaries

Media upload/quarantine/scanning, operational identity federation/MFA, authoritative partner evidence, fleet-specific GPS thresholds, measured delivery ETA and route bindings require their separate integrations. No image is marked uploaded or clean by this workflow. GPS consent here is a recorded software declaration; deployments need their real consent/mission-assignment policy and retention enforcement. Regional mission aggregation is not yet implemented. High-rate pagination and concurrent-writer load qualification remain deployment work; unique database keys and transactions protect basic retries. Authentication middleware must enforce origin/CSRF policy and no-store responses when registering this router.

