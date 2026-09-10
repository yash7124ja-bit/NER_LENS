# NER LENS backend engineering contracts (v1)

**Status:** frozen v1 contract for independent backend agents  
**Audience:** API, ingestion, routing, risk, mission/GPS, alerts, storage and verification implementers  
**Transport:** HTTPS JSON/GeoJSON; media uploads are separate binary requests; persisted alerts use cursor-based retrieval  
**Versioning:** all public endpoints are under `/v1`; incompatible changes require `/v2`  
**Time zone:** clients send explicit RFC 3339 offsets; server stores/returns UTC `Z`

This is a backend contract. It does not define a frontend, chatbot, LLM/RAG, agent runtime or presentation layer.

All UUIDs, coordinates, distances, times, probabilities, and route values in JSON examples are synthetic contract fixtures. They are not measured NER LENS results or current corridor conditions.

## 1. Common wire rules

### JSON conventions

- UTF-8 JSON; unknown request fields are rejected unless an endpoint explicitly permits an extension object.
- IDs are opaque lowercase UUIDv4 strings unless marked `external_id` or `source_record_id`.
- Timestamps are RFC 3339 with offset on input and UTC `Z` on output, for example `2026-09-08T09:18:22Z`.
- Durations are integer seconds; distances are integer metres; probabilities are numbers in `[0,1]`.
- Enumerations are lowercase `snake_case` strings.
- Coordinates use GeoJSON order `[longitude, latitude]`, EPSG:4326. API geometry is GeoJSON, not WKT.
- `null` means known absent/not applicable. Missing fields mean the producer did not supply them; do not convert missing numeric values to zero.
- Pagination uses opaque `next_cursor`; default 50, maximum 200.
- Responses include `request_id` either as a top-level field or `X-Request-ID` header; errors always include it.

### Required headers

```text
Authorization: Bearer <OIDC access token>
Content-Type: application/json
X-Request-ID: <optional opaque request id>
Idempotency-Key: <required on every POST/PUT/PATCH that mutates state>
```

`Idempotency-Key` is 1–255 bytes. The server stores the first status code and body hash for at least 24 hours and replays the original response for an identical request. Reuse with a different body returns `409 idempotency_conflict`.

## 2. Auth context and authorization

The API validates OIDC issuer, audience, signature, expiry and token type. A server-created `AuthContext` is the only source of actor identity:

```json
{
  "actor_id": "uuid",
  "actor_type": "user",
  "roles": ["dispatcher"],
  "jurisdiction_ids": ["uuid"],
  "mission_ids": [],
  "session_id": "uuid",
  "token_issued_at": "2026-09-08T09:00:00Z"
}
```

Supported roles:

| Role | Allowed v1 actions |
|---|---|
| `field_reporter` | Create/view own pending reports; upload own media; submit GPS only for assigned active mission |
| `reviewer` | Review evidence and conflicts in assigned jurisdiction |
| `dispatcher` | Create missions, compare routes and view authorized mission/vehicle data |
| `district_officer` | Publish/expire status decisions and approve alerts in assigned jurisdiction |
| `regional_viewer` | Aggregated/read-only corridor and mission view; no precise GPS |
| `system_admin` | Configuration, users and health; no implicit status approval |
| `ingestion_service` | Create source snapshots/evidence through adapter commands; no status publication |

Every object read and mutation enforces jurisdiction/mission scope server-side. Role checks are necessary but not sufficient: the target object must be in the actor's scope. The actor cannot supply `actor_id`, `roles` or jurisdiction claims in a request body.

## 3. Error contract

All non-2xx responses use:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "human-readable, non-sensitive summary",
    "details": [{"field": "origin", "reason": "invalid_geometry"}],
    "retryable": false,
    "request_id": "uuid"
  }
}
```

| HTTP | Code | Meaning |
|---:|---|---|
| 400 | `invalid_request` | JSON, enum, geometry, timestamp or cross-field validation failed |
| 401 | `unauthenticated` | Missing/invalid/expired token |
| 403 | `forbidden` | Valid identity lacks role or object/jurisdiction scope |
| 404 | `not_found` | Target is absent or intentionally undiscoverable |
| 409 | `conflict` | State transition, graph version or domain conflict |
| 409 | `idempotency_conflict` | Same key used with a different body |
| 413 | `payload_too_large` | Media/request exceeds configured limit |
| 415 | `unsupported_media_type` | Media/content type not permitted |
| 422 | `unprocessable_entity` | Structurally valid but semantically impossible |
| 429 | `rate_limited` | Caller/device/endpoint limit exceeded |
| 502 | `upstream_unavailable` | Source or router unavailable for this operation |
| 503 | `degraded` | Service cannot provide a verified answer in current mode |
| 500 | `internal_error` | Unexpected server failure; no sensitive details |

Retry only when `retryable=true`, preserving the same idempotency key. `no_verified_feasible_route`, stale data and `insufficient_evidence` are valid domain outcomes represented in successful response envelopes, not server failures or route recommendations.

## 4. Shared DTOs

### `EvidenceRef`

```json
{
  "evidence_id": "uuid",
  "type": "field_report",
  "source": "field_app",
  "source_record_id": "uuid-or-provider-id",
  "review_state": "accepted",
  "observed_at": "2026-09-08T09:00:00Z",
  "source_published_at": null,
  "retrieved_at": "2026-09-08T09:18:22Z",
  "valid_until": "2026-09-08T15:00:00Z",
  "geometry": {"type": "Point", "coordinates": [92.7, 25.4]},
  "confidence": 0.8,
  "snapshot_sha256": "64-hex",
  "quality_flags": []
}
```

### `OperationalStatus`

```json
{
  "value": "restricted",
  "vehicle_scope": ["rigid_truck"],
  "direction": "forward",
  "effective_at": "2026-09-08T09:30:00Z",
  "valid_until": "2026-09-08T15:00:00Z",
  "authority": {"actor_id": "uuid", "role": "district_officer"},
  "reason_code": "flooded",
  "evidence_ids": ["uuid"],
  "decision_id": "uuid"
}
```

### `RiskOutlook`

```json
{
  "state": "elevated",
  "probability": 0.42,
  "horizon_seconds": 21600,
  "issued_at": "2026-09-08T09:20:00Z",
  "model_version": "hazard_rule_v1",
  "feature_snapshot_id": "uuid",
  "explanation": ["72h rainfall is high", "last accepted passability observation is stale"],
  "abstention_reason": null
}
```

`RiskOutlook.state=insufficient_evidence` requires `probability=null` and a non-null `abstention_reason`. Risk never contains an operational status transition.

## 5. Public API surface

### Health

#### `GET /health/live`

Unauthenticated process liveness. Returns `200` when the process can respond:

```json
{"status":"live","request_id":"uuid"}
```

#### `GET /health/ready`

Returns `200` only when migrations are compatible and the database is reachable. Returns `503` otherwise. Router/model are reported as components, not a reason to claim readiness if the API itself is healthy.

#### `GET /health/sources`

Authenticated `reviewer`, `district_officer`, `regional_viewer` or `system_admin`. Returns source name, last successful retrieval, source event age, health (`healthy|stale|failed|quarantined`), parser version and last error code. Never returns credentials or raw sensitive payloads.

### Corridor state

#### `GET /v1/corridors/{corridor_id}/state`

Query: `at` optional; `vehicle_profile` optional; `include_evidence` default false; `cursor`, `limit`.

Response:

```json
{
  "corridor_id":"uuid",
  "corridor_version_id":"uuid",
  "as_of":"2026-09-08T09:30:00Z",
  "segments":[{
    "segment_id":"uuid",
    "external_refs":[{"source":"osm","id":"way/123"}],
    "geometry":{"type":"LineString","coordinates":[]},
    "operational_status":{"value":"open","vehicle_scope":["all"],"valid_until":"2026-09-08T12:00:00Z"},
    "risk":{"state":"elevated","probability":0.42,"horizon_seconds":21600},
    "evidence_age_seconds":3600,
    "source_health":"healthy",
    "evidence":[/* omitted unless requested */]
  }],
  "next_cursor":null
}
```

No recent valid status is represented as `unknown` or expired, never as a new `open`. Regional viewers receive only authorized aggregate/segment data.

### Route comparison

#### `POST /v1/routes/compare`

Request:

```json
{
  "corridor_id":"uuid",
  "graph_version_id":"uuid",
  "origin":{"type":"Point","coordinates":[91.7,26.1]},
  "destination":{"type":"Point","coordinates":[92.8,24.8]},
  "vehicle_profile":"rigid_truck",
  "mission_id":null,
  "departure_at":"2026-09-08T10:00:00Z",
  "deadline_at":"2026-09-08T22:00:00Z",
  "alternative_limit":3
}
```

Response:

```json
{
  "comparison_id":"uuid",
  "graph_version_id":"uuid",
  "policy_id":"uuid",
  "policy_version":"string",
  "mode":"verified|degraded|insufficient_evidence|no_verified_feasible_route",
  "recommended_route_id":"uuid-or-null",
  "routes":[{
    "route_id":"uuid",
    "geometry":{"type":"LineString","coordinates":[]},
    "segment_ids":["uuid"],
    "distance_m":123456,
    "travel_time_seconds":{"p50":14400,"low":13200,"high":18000,"basis":"baseline"},
    "risk_exposure":{"probability_weighted_minutes":38,"state":"elevated"},
    "uncertainty_score":0.35,
    "blocked_segment_ids":[],
    "key_evidence_ids":["uuid"],
    "reason":"Adds time but avoids a stale high-risk hill segment",
    "score_components":{"travel_minutes":240,"risk":38,"uncertainty":12,"staleness":8,"deadline_penalty":0}
  }],
  "warnings":[],
  "blocking_constraints":[],
  "request_id":"uuid"
}
```

The API must not return `recommended_route_id` when a hard constraint is violated, required evidence is absent beyond policy, or the route is only a stale/unverified cache. No feasible route returns `200` with `mode=no_verified_feasible_route`, an empty `routes` list, and explicit `blocking_constraints`. Router failure remains `502 upstream_unavailable`.

#### `RouteVerificationPolicy`

Each comparison records the immutable policy ID and version used. The policy contains: audited graph-currency rule; critical source classes; source-specific maximum ages; status-validity rule; minimum evidence coverage; applicability by segment, direction and vehicle profile; and whether a degraded result may be recommended. M0 records the numeric ages and coverage thresholds from the source/corridor audit and names the operational owner who approved them; implementation must not invent global defaults.

Policy outcomes are deterministic:

- `verified`: graph is current, all hard constraints were evaluated, and required coverage/freshness passes;
- `degraded`: only non-critical inputs are stale or missing, and a recommendation is returned only when the policy explicitly permits it;
- `insufficient_evidence`: a critical source is stale/missing or coverage is below threshold; alternatives may be shown, but `recommended_route_id` is null;
- `no_verified_feasible_route`: every candidate is hard-excluded; `routes` is empty and `blocking_constraints` explains why.

If a threshold, source classification, or operational owner remains unresolved, the conservative result is `insufficient_evidence` with no recommendation. Replay tests must cover all four outcomes and policy-version reproducibility.

### Field reports

#### `POST /v1/field-reports`

Request:

```json
{
  "client_report_id":"uuid",
  "client_sequence":17,
  "segment_id":"uuid-or-null",
  "observed_at":"2026-09-08T09:00:00+05:30",
  "geometry":{"type":"Point","coordinates":[92.7,25.4]},
  "accuracy_m":12,
  "status_claim":"blocked",
  "condition_code":"landslide",
  "note":"One lane blocked",
  "device_id":"uuid",
  "clock_offset_seconds":-4
}
```

The server sets `received_at`, validates reporter scope and returns `201`:

```json
{"field_report_id":"uuid","client_report_id":"uuid","sync_state":"accepted_for_review","review_state":"unreviewed","received_at":"2026-09-08T09:18:22Z","media_state":"none","request_id":"uuid"}
```

The response does not mean the report changed status. Replaying the same client ID/body returns the original response. Same ID/different body returns `409 idempotency_conflict`.

#### `PUT /v1/field-reports/{field_report_id}/media/{slot}`

Request is binary with `Content-Type` restricted to approved image types, `Content-Length` within policy, `X-Media-SHA256`, and idempotency key. Response:

```json
{"media_object_id":"uuid","sha256":"64-hex","scan_state":"pending|clean|rejected|error","media_state":"complete|incomplete","request_id":"uuid"}
```

Metadata and media are separate. Failed/partial media remains visible as incomplete and cannot be treated as present by a reviewer.

The media boundary exposes `ObjectStore.put_quarantined()` and `MediaScanner.scan()` operations. The server recomputes SHA-256 and validates size, declared type and successful decode before scanning. Only `scan_state=clean` is eligible for protected retrieval; pending, rejected and error states fail closed. Local test adapters cannot support a production-clean claim.

### Evidence review and status

#### `POST /v1/reviews/{evidence_id}`

Request:

```json
{"action":"accept|reject|merge|needs_clarification","note":"string","merge_into_evidence_id":null}
```

Only `reviewer` or a more privileged scoped role may review. The action appends a review revision and audit event; it does not erase the original evidence.

#### `POST /v1/status-decisions`

Request:

```json
{
  "segment_id":"uuid",
  "status":"open|restricted|closed|unknown",
  "vehicle_scope":["all"],
  "direction":"forward|reverse|both",
  "reason_code":"authority_order|flooded|landslide|damage|restriction|reopened|expiry",
  "evidence_ids":["uuid"],
  "effective_at":"2026-09-08T09:30:00Z",
  "valid_until":"2026-09-08T15:00:00Z",
  "note":"string"
}
```

`district_officer` or an explicitly configured authority may publish status in scope. `closed`/`restricted` requires at least one accepted or authoritative evidence reference unless configured as an authority order. `risk_prediction` IDs are not sufficient evidence for closure. `valid_until` is required for non-permanent v1 decisions. Response:

```json
{"decision_id":"uuid","segment_id":"uuid","status":"closed","effective_at":"2026-09-08T09:30:00Z","valid_until":"2026-09-08T15:00:00Z","audit_event_id":"uuid","request_id":"uuid"}
```

Allowed transitions are `unknown→open|restricted|closed`, `open→restricted|closed|unknown`, `restricted→closed|open|unknown`, `closed→restricted|open|unknown` only with authority/review and audit. Expiry transitions to `unknown`, never automatically to `open`.

### Missions and GPS

#### `POST /v1/missions`

Request:

```json
{
  "cargo_class":"medicine",
  "priority":"routine|high|emergency",
  "origin":{"type":"Point","coordinates":[]},
  "destination":{"type":"Point","coordinates":[]},
  "delivery_window":{"start":"2026-09-08T10:00:00Z","end":"2026-09-08T22:00:00Z"},
  "vehicle_profile":"rigid_truck",
  "vehicle_id":"uuid-or-null",
  "corridor_id":"uuid",
  "route_id":"uuid-or-null",
  "gps_consent":{"basis":"mission_assignment|explicit_consent","recorded_at":"2026-09-08T09:30:00Z"}
}
```

Response `201` includes `mission_id`, `state=planned`, `graph_version_id`, `created_at`, and the assigned scope. Mission creation never implies GPS is active until explicitly started.

#### `POST /v1/missions/{mission_id}/start`

No body beyond optional `device_id`. Requires dispatcher or assigned field user scope and recorded GPS consent. Returns state `active`, `started_at`, `graph_version_id` and `gps_session_id`.

#### `POST /v1/missions/{mission_id}/positions`

Request:

```json
{
  "device_id":"uuid",
  "sequence_start":100,
  "points":[
    {"sequence":100,"captured_at":"2026-09-08T10:00:00+05:30","geometry":{"type":"Point","coordinates":[]},"accuracy_m":8,"speed_mps":12.4,"heading_deg":90}
  ]
}
```

Response includes accepted, duplicate, rejected and flagged sequence lists plus `received_at`. Batch replay is idempotent by mission + device + sequence and request key. The service preserves client capture time and records server receipt time. It never silently interpolates or snaps away an impossible jump.

#### `GET /v1/missions/{mission_id}`

Returns mission state, graph version, route reference, checkpoints, last fix and age, delay estimate basis, and authorized GPS precision. Regional viewers receive aggregate progress only.

### Alerts and model metadata

#### `GET /v1/alerts`

Authorized clients retrieve canonical persisted alerts using `cursor`, `limit`, optional `created_after`, acknowledgement state, severity, mission, segment, and jurisdiction filters. The response contains alert ID, severity, scoped mission/segment references, template/version, locale, validated variables, created time, delivery state, acknowledgement, and `next_cursor`.

SSE may be added later as an advisory delivery interface. It must use persisted alert IDs and cursor recovery; it never becomes the canonical alert store.

#### `GET /v1/models/current`

Returns model version, target, horizon, training cutoff, feature checksum, baseline/candidate metrics (or `not_measured`), domain, known failures and abstention rules. It must not claim validation numbers that are absent from the model card.

#### `GET /v1/audit`

Scoped reviewers/officers/admins may query by target, actor, action, time range and cursor. Raw media and precise GPS are not returned through this generic endpoint.

## 6. Internal adapter and service contracts

### Source adapter

```python
fetch(run_context) -> RawSnapshot
parse(snapshot) -> list[AdapterRecord]
normalize(record) -> EvidenceDraft
```

`AdapterRecord` fields are:

```json
{
  "source":"string",
  "source_record_id":"string",
  "observed_at":"timestamp",
  "source_published_at":"timestamp-or-null",
  "retrieved_at":"timestamp",
  "geometry":"GeoJSON geometry",
  "payload":{},
  "units":{},
  "quality_flags":[],
  "snapshot_sha256":"64-hex",
  "parser_version":"git-sha"
}
```

The adapter is responsible for source-specific parsing, not route/status policy. Scheduled jobs create a `source_run` with run ID, cadence, outcome, counts and error code. A failed/quarantined run does not create negative evidence.

### Routing adapter

```python
compare_routes(
    graph_version_id,
    vehicle_profile,
    origin,
    destination,
    hard_excluded_segment_ids,
    alternative_limit,
) -> GraphRouteSet
```

The adapter returns graph-valid alternatives and raw leg/edge references. It does not inspect weather, set status or decide the recommended route. The routing domain joins effective status/risk/evidence and creates `RouteComparison`.

### Risk service

```python
predict(segment_ids, issue_time, horizon_seconds, evidence_snapshot_id) -> list[RiskPrediction]
```

Inputs are point-in-time features only. Output is deterministic for the same model, feature snapshot and input. It must report `insufficient_evidence` when freshness/schema/domain gates fail. Model output is never accepted by `status` as authority.

### Alert service

```python
evaluate(material_event) -> list[AlertDraft]
deliver(alert_id, recipient_scope) -> list[DeliveryResult]
```

Rules are versioned and deterministic. Template variables are schema-validated. Delivery failure changes delivery state and emits an audit event; it does not roll back the status/mission event.

## 7. Storage contract

Minimum relational tables and required uniqueness:

| Table | Required keys/invariants |
|---|---|
| `corridor_version` | unique name+version; one active version per corridor |
| `road_segment` | unique corridor_version+internal ID; geometry SRID 4326; external refs retained |
| `source_snapshot` | unique source+sha256; immutable body metadata |
| `source_run` | unique run ID; outcome and parser version recorded |
| `evidence` | immutable; source snapshot/revision reference; observed/retrieved times |
| `segment_evidence` | unique segment+evidence+association method; validity interval |
| `status_decision` | append-only; effective/expiry; segment/direction/vehicle scope |
| `route_verification_policy` | immutable policy ID+version; graph-currency, source-age, coverage, applicability and degraded-recommendation rules |
| `route_decision` | immutable comparison ID; request hash, graph/policy/feature/evidence versions, alternatives/result, recommendation and actor/request audit references |
| `risk_prediction` | unique segment+issued_at+horizon+model_version+feature snapshot |
| `mission` | graph version pinned; state transition audit |
| `gps_batch` / `gps_observation` | unique mission+device+sequence; raw point retained |
| `field_report` | unique client_report_id; review/sync state separate |
| `media_object` | unique sha256/storage key; scan state required |
| `idempotency_record` | unique actor+method+path+key; response status/body hash |
| `alert` | unique dedupe key; template/version/recipient scope |
| `audit_event` | append-only, request ID, before/after hashes |

Database migrations must enforce these invariants where possible. Application checks cover jurisdiction, authority and cross-row policy. Deleting or updating status/evidence/audit history is not a v1 operation.

## 8. Contract test matrix

Every independent implementation must provide at least one executable fixture for each row:

| Contract | Minimum test |
|---|---|
| Time/freshness | Retrieval of old payload is stale; expired status becomes unknown, not open |
| Evidence/status separation | High model risk and rainfall warning cannot create closed status |
| Precedence/conflict | Conflicting reports persist; authority decision wins without deleting them |
| Idempotency | Same field-report/GPS/media request replays one result; different body conflicts |
| Authorization | Cross-jurisdiction read/write and role escalation are rejected |
| Geometry | Wrong coordinate order, invalid CRS/out-of-bounds and buffer edge cases fail safely |
| Source adapter | Missing units, ambiguous zone, schema drift and HTTP 200 old data are quarantined |
| Routing | Closed applicable segment is never recommended; no-feasible route is explicit |
| Mission/GPS | Out-of-order sequence is retained once; impossible jump is flagged, not smoothed |
| Offline/media | Metadata accepted while media incomplete; failed scan cannot be approved as present |
| Alerts | Material event dedupes; severity increase is not suppressed by prior acknowledgement |
| Audit | Status, route, review and alert changes reconstruct actor, reason and before/after hashes |
| Risk | Baseline-first output, point-in-time cutoff and model abstention are reproducible |
| Degraded mode | Router/model/source failure returns documented code and never fabricated certainty |

## 9. Frozen v1 acceptance criteria

- `POST /v1/status-decisions` is the only path to operational status.
- Every status, risk, route and alert response exposes source/evidence IDs, timestamps, scope and freshness or an explicit reason for absence.
- Weather/hazard/model evidence cannot directly create `closed`.
- Guwahati–Silchar is labelled provisional until corridor-audit evidence is stored; configuration supports replacing it.
- A mission remains on its graph version until explicit recalculation.
- All mutations are idempotent and all sensitive reads are scope checked.
- Source snapshots, evidence, status history, GPS originals and audit events are immutable.
- No stale/failed feed is rendered as healthy; no missing observation is treated as a negative/open label.
- Baseline risk remains the operational fallback until blocked evaluation and calibration pass the promotion gate.
- The backend can replay the complete mission/report/review/status/route/alert/audit flow without manual database edits.
