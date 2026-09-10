# NER LENS Milestone Task Specifications

> **For agentic workers:** Use `docs/PARALLEL_EXECUTION_PLAN.md` for ownership, synchronization, merge order, rollback, and the forced-single-working-tree procedure. This document contains specifications only; it does not authorize implementation outside the files listed in each task.

**Goal:** Build the smallest reviewable NER LENS decision-support slice for an essential-medicine mission on the Guwahati–Silchar corridor, then add offline evidence, ingestion, risk, conditional ML, and release hardening without claiming unverified coverage.

**Architecture:** A backend-only FastAPI modular monolith with PostgreSQL/PostGIS, Alembic, a self-hosted GraphHopper sidecar, scheduled source adapters, and a versioned in-process risk artifact. Operational status and predictive risk remain separate; all state changes are auditable. A future client consumes the published API and sync contracts.

**Tech Stack:** Python 3.13 compatibility target; FastAPI/Pydantic v2; SQLAlchemy 2; Alembic; psycopg 3; GeoAlchemy2/PostGIS; httpx/Typer; GraphHopper; pytest/Ruff/mypy; Docker Compose.

**Source documents:** `../../SIH-26002-TECH-STACK-IMPLEMENTATION-AND-VALIDATION.md` and `../../SIH-26002-AI-Based-Smart-Logistics-and-Accessibility-Intelligence-Platform-for-North-Eastern-Region-NER.md`.

## Non-negotiable project rules

- The prototype is one corridor, one essential-medicine mission, one defensible alternative, and three vehicle profiles: `light_goods`, `rigid_truck`, `emergency`.
- Operational status is exactly `open | restricted | closed | unknown`; only an authorized status decision can change it. Weather, hazard, and model outputs never close a road.
- Risk is a bounded probability or `insufficient_evidence`, initially six-hour horizon. A candidate model is conditional on labels and must not replace the transparent baseline until the promotion gate passes.
- Every external fact preserves observation/published/retrieved time, raw snapshot hash, source, parser version, geometry, quality flags, and license/terms note.
- Unknown, stale, failed, conflict, and media-incomplete states are first-class. Absence of a report is not a negative/open label.
- Every mutation accepts an idempotency key; server time and client observation time are both retained.
- No Kubernetes, Kafka, vector database, blockchain, LLM, computer vision, data lake, autonomous dispatch, public turn-by-turn navigation, or region-wide coverage is part of these milestones.
- All migrations are owned and authored by Path A. Sol may request schema changes but cannot edit Alembic files.
- Any replay, simulator, or synthetic record is visibly labelled and cannot be presented as live coverage or model validation.

## Shared interface registry

[CONTRACTS.md](./CONTRACTS.md) is the only canonical source for field names, enums, wire shapes, errors, and endpoint behavior. This table assigns producers and consumers without duplicating those definitions.

| Interface | Producer | Consumers |
|---|---|---|
| `AuthContext` | Path A identity implementation under Sol contract | every protected service |
| `CorridorVersion`, `RoadSegment` | Path A | evidence, status, routing, risk, missions |
| `SourceSnapshot`, `EvidenceRef`, `ResolvedSegmentState` | Path A | status, risk, routing, alerts |
| `OperationalStatus`, `ReviewAction` | Path A | routing, alerts, API composition |
| `Mission`, `PositionBatch` | Path B | routing, alerts, API composition |
| `RiskOutlook` | Path B | routing, alerts, corridor state |
| `RouteComparison`, `RouteAlternative` | Path B | missions, alerts, API composition |
| `Alert`, `AlertDelivery` | Path B | API composition and authorized clients |
| error envelope, idempotency, OpenAPI version | Sol | all modules |

## Terra gates

**Terra P0 — evidence and safety feasibility, before M1 implementation.** Pass only when the team has a dated corridor/graph audit, two route hypotheses with restriction checks, a named status authority and evidence reviewer, source access/terms and replay fallbacks, a positive-event/ground-truth plan, and an essential-medicine mission. Fail means stop or change corridor; do not compensate with fabricated data.

**Terra P1 — operational release safety, before M6 release or any conditional model promotion.** Pass only when route replay has zero applicable closure/vehicle violations, status provenance is reconstructible, stale/failed feeds abstain or degrade honestly, auth scope tests pass, offline controlled sync has zero loss and duplicate canonical records, alert templates are reviewed, backups restore, and model claims are baseline-relative with blocked evaluation. P1 failure blocks release and requires rollback to the last passing baseline.

## Milestones and tasks

Each task has the required fields: ID, objective, owner, dependencies, inputs, outputs, allowed/forbidden files, consumed/produced interfaces, acceptance criteria, tests, validation/integration, and completion condition.

### M0 — Reconnaissance and corridor audit

Outcome: a safe proof boundary and a shared contract baseline. Terra P0 is the exit gate.

#### A-M0-01 — Corridor, source, and label feasibility ledger

- **Objective:** Select or reject Guwahati–Silchar NH-27 with the NH-6 direction as an alternative using evidence, access, label, reviewer, and mission criteria.
- **Owner:** Path A; reviewer: Sol; gate: Terra P0.
- **Dependencies:** none.
- **Inputs:** dated OSM/Geofabrik extract; NHAI/NHIDCL references; IMD, GSI, CWC, ASDMA and SACHET access notes; partner/reviewer interview; prototype mission.
- **Outputs:** `docs/decisions/corridor-audit.md` (only after M1 directory ownership is confirmed), source/terms ledger, segment-band list, label feasibility decision, P0 decision record.
- **Allowed files:** `docs/decisions/corridor-audit.md`, `data/manifests/*` fixture manifests, `tests/replay/*` small licensed/curated fixtures.
- **Forbidden files:** application code, migrations, lockfiles, production credentials, unlicensed raw data, any status table or model result.
- **Consumes:** source facts and corridor assumptions from the two primary docs.
- **Produces:** `corridor_id`, six named audit bands, route buffer `5 km`, hazard-context default `20 km`, administrative-unit list, source health/terms and fallback labels, and audited numeric inputs for `RouteVerificationPolicy`.
- **Acceptance criteria:** both candidates are routable or an explicit rejection reason is recorded; truck/access restrictions and construction tags are checked; no planned road is treated as open; at least one reviewer/authority path and one positive-event evidence path are named; all integrations are marked direct/account/portal/partner.
- **Tests:** manifest checksum/required-field check; fixture test that unlicensed/private records are rejected; audit checklist test requiring mission, reviewer, labels, terms, and fallback.
- **Validation/integration:** Sol reviews interface implications; Terra reviewer signs P0 or records corridor change; B consumes route buffers and graph version.
- **Completion condition:** signed P0 decision and immutable audit manifest exist, or work is explicitly stopped/redirected.

#### B-M0-01 — Route and GraphHopper feasibility audit

- **Objective:** Prove that current OSM data can represent two candidate paths and the three vehicle profiles without silently ignoring restrictions.
- **Owner:** Path B.
- **Dependencies:** A-M0-01 draft corridor bounds and candidate endpoints.
- **Inputs:** OSM extract, candidate endpoints, GraphHopper profile documentation, restriction audit checklist.
- **Outputs:** graph audit report, candidate route identifiers, profile/restriction coverage matrix, labelled route replay fixture.
- **Allowed files:** `data/corridor/*` audit/config fixtures, `tests/replay/routing/*`, `docs/decisions/route-audit.md`.
- **Forbidden files:** Alembic migrations, identity/evidence tables, lockfiles, real GPS, route claims beyond audited graph version.
- **Consumes:** `CorridorVersion` draft and route buffer from A-M0-01.
- **Produces:** `RouteComparison` fixture with `graph_version`, hard constraints, alternatives, and known missing restriction flags.
- **Acceptance criteria:** topology, surface, bridge/tunnel, access, `maxheight`, `maxweight`, `hgv`, construction, turn and direction checks are recorded; one route is not removed by risk alone; missing legality data is visible; GraphHopper unavailability has a deterministic fixture path.
- **Tests:** route fixture tests for closed edge, vehicle restriction, direction, and no-feasible-route; checksum test for graph extract.
- **Validation/integration:** A verifies segment IDs can receive status; Sol verifies route contract; Terra P0 reviews the route evidence.
- **Completion condition:** route audit is signed and labelled replay alternatives are available.

#### S-M0-01 — Contract and repository baseline

- **Objective:** Establish the shared contract vocabulary, ownership map, repository layout, and baseline verification command before dependency changes.
- **Owner:** Sol.
- **Dependencies:** none; incorporate A/B M0 assumptions as they arrive.
- **Inputs:** two primary docs; this milestone document; empty repository state.
- **Outputs:** contract registry, ownership manifest, baseline CI/check command, initial OpenAPI placeholder policy (not a generated snapshot), schema-request template, and a dated official SIH-26002 snapshot plus requirement diff; if official access is unavailable, a signed human risk-acceptance record replaces the snapshot but blocks official-traceability claims.
- **Allowed files:** `docs/*`, root CI/config only if baseline exists; no runtime implementation.
- **Forbidden files:** Alembic migrations, domain models, app endpoints, lockfile/dependency edits, secrets.
- **Consumes:** named interfaces in this document.
- **Produces:** canonical names/types, versioned `RouteVerificationPolicy`, and `schema_request` template with compatibility classification.
- **Acceptance criteria:** every boundary has one owner; A is the only migration owner; B can build against interface names; the official snapshot/diff or signed risk acceptance exists; policy source classes, source-specific maximum ages, coverage, graph currency, applicability, degradation rule and approving operational owner are recorded; Sol's baseline check runs without adding runtime dependencies; no implementation is implied.
- **Tests:** markdown/link/path lint; contract registry duplicate-name check; baseline clean-tree check.
- **Validation/integration:** publish the initial contract freeze and resolve discrepancies with A/B before M1.
- **Completion condition:** both path owners acknowledge the same contract, required official evidence/risk acceptance exists, the baseline check is green, the human accepts the seven specifications, and Sol/human creates the first shared baseline commit. No worktree or runtime task may start from an uncommitted tree.

### M1 — Foundation, identity, corridor, and migration base

Outcome: a bootable backend skeleton with a versioned corridor and scoped actors. Every schema change is an Alembic migration authored by A.

#### A-M1-01 — API/database foundation and initial migrations

- **Objective:** Create the minimum FastAPI/SQLAlchemy/PostGIS/Alembic foundation and migration chain for identity, corridor, audit, idempotency, and health checks.
- **Owner:** Path A.
- **Dependencies:** S-M0-01; Terra P0 pass; A-M0-01.
- **Inputs:** pinned baseline runtime choice; `AuthContext`, `CorridorVersion`, `RoadSegment`; PostGIS requirements.
- **Outputs:** initial `pyproject.toml` and Python lockfile, migration chain `0001_foundation` and subsequent A-owned revisions, DB session/transaction boundary, health router for `/health/live` and `/health/ready`, and config names only in `.env.example`.
- **Allowed files:** `pyproject.toml`, `uv.lock` or equivalent initial Python lockfile, `.env.example`, `src/ner_lens/config.py`, `src/ner_lens/db.py`, `src/ner_lens/health.py`, `src/ner_lens/common/**`, `src/ner_lens/identity/models.py`, `src/ner_lens/corridor/models.py`, `migrations/**`, `tests/path_a/foundation/**`.
- **Forbidden files:** any frontend repository, `models/**`, GraphHopper configs, B-owned service internals, production secrets.
- **Consumes:** shared contracts and P0 corridor IDs.
- **Produces:** tables for actor/district/session references, corridor versions, road segments, audit events, idempotency keys; migration command contract.
- **Acceptance criteria:** fresh DB upgrades cleanly; PostGIS geometry is EPSG:4326 at API boundary; constraints reject invalid status values/geometry outside bounds where configured; health distinguishes DB-ready from live; migration downgrade is tested on disposable DB.
- **Tests:** pytest repository/session test; migration up/down on disposable PostGIS; invalid geometry/status tests; health readiness test.
- **Validation/integration:** B can create a session/transaction and reference a corridor version; Sol wires and verifies OpenAPI health paths; no migration is edited after merge without a new revision. After this baseline, only Sol edits dependency declarations/locks and only Path A edits migrations.
- **Completion condition:** baseline migration and foundation tests pass on a clean checkout.

#### A-M1-02 — Identity, roles, district scope, and authorization primitive

- **Objective:** Implement server-side role and object-scope checks for officials, reviewers, dispatchers, field reporters, regional viewers, and admins.
- **Owner:** Path A.
- **Dependencies:** A-M1-01; `AuthContext` contract.
- **Inputs:** role matrix and district/mission scope from primary docs.
- **Outputs:** identity service, actor context dependency, authorization decision function, audit events for denied/allowed protected actions.
- **Allowed files:** `src/ner_lens/identity/**`, `src/ner_lens/security/**`, `migrations/**` new revision only, `tests/path_a/identity/**`.
- **Forbidden files:** route scoring, model code, alert delivery, frontend auth UI, direct OIDC provider integration beyond interface stub.
- **Consumes:** `AuthContext`, `CorridorVersion`, `Mission` scope reference.
- **Produces:** `authorize(actor, action, resource_scope) -> Decision`; role constants; protected endpoint dependency.
- **Acceptance criteria:** district and mission isolation is enforced server-side; hiding UI is not treated as authorization; admin cannot approve operational status by role alone; denied access is audited without secrets or precise GPS.
- **Tests:** authorization matrix for each role/action/scope; object-level access tests; replayed token/session expiry test.
- **Validation/integration:** Sol checks error envelope and OpenAPI security metadata; B wires mission/routing endpoints only through this primitive.
- **Completion condition:** all protected fixture endpoints pass the matrix and A records the OIDC integration boundary.

#### A-M1-03 — Corridor version and segment import

- **Objective:** Import the audited graph references into stable operational segments with geometry, direction, authority, constraints, and graph version.
- **Owner:** Path A.
- **Dependencies:** A-M1-01; A-M0-01; B-M0-01.
- **Inputs:** dated graph checksum, six audit bands, segment rules at junctions/bridges/authority boundaries/bottlenecks.
- **Outputs:** `CorridorVersion` and `RoadSegment` records, import manifest, stable internal IDs, seed data with no personal information.
- **Allowed files:** `src/ner_lens/corridor/**`, `data/corridor/**`, `migrations/**` new revision, `tests/path_a/corridor/**`.
- **Forbidden files:** route ranking, risk features, source adapters, raw private traces, planned infrastructure as open road.
- **Consumes:** `CorridorVersion`, `RoadSegment` and route audit fixture.
- **Produces:** `get_active_corridor()`, `list_segments(corridor_id)`, geometry/version lookup used by all modules.
- **Acceptance criteria:** all mission-route edges map to stable segments; directional/bridge segmentation is preserved; external references and graph checksum are retained; invalid/out-of-bounds geometry is quarantined; seed can be recreated without manual DB edits.
- **Tests:** CRS/buffer/boundary tests; import idempotency; graph upgrade mapping test; bridge/directional segment fixture.
- **Validation/integration:** B resolves route edges to segment IDs; Sol confirms GeoJSON schema; A migration test passes.
- **Completion condition:** active corridor seed and import manifest load on a clean DB with no manual edits.

#### A-M1-04 — Path B persistence schema delivery

- **Objective:** Deliver the A-owned relational schema required for Path B services before Path B writes persistence code.
- **Owner:** Path A; contract approval: Sol.
- **Dependencies:** A-M1-01; S-M0-01 contract freeze.
- **Inputs:** canonical storage contracts for vehicle, mission, GPS, risk/model and alerts; exact keys, nullability, scope, retention and uniqueness rules.
- **Outputs:** A-owned models and an Alembic revision for `vehicle`, `mission`, `gps_batch`, `gps_observation`, `route_verification_policy`, `route_decision`, `risk_prediction`, `model_version`, `alert` and `alert_delivery`.
- **Allowed files:** `src/ner_lens/persistence/**`, `migrations/**`, `tests/path_a/schema/**`, `docs/schema-requests/**` acknowledgements.
- **Forbidden files:** Path B services, route scoring, alert rules/templates, shared DTOs, application wiring, lockfiles.
- **Consumes:** canonical storage contract and Sol-approved compatibility classification.
- **Produces:** migration-backed repository/table contract that Path B can consume without editing migrations.
- **Acceptance criteria:** fresh upgrade/downgrade succeeds; foreign keys target existing actor/corridor/segment records; mission graph version and GPS uniqueness are enforced; immutable route policy/decision records retain request hash, graph/policy/feature/evidence versions and result; alert/risk uniqueness and sensitive-data scope are testable; no business behavior is embedded in persistence models.
- **Tests:** disposable PostGIS migration up/down; constraint/uniqueness tests for mission, GPS sequence, route policy/decision identity, risk identity and alert delivery; model-registry import test.
- **Validation/integration:** Sol checks contract parity; Path B runs a persistence smoke fixture before B-M1-01; later schema needs use the schema-request protocol.
- **Completion condition:** the migration is green from a clean database and Path B acknowledges the repository/table contract.

#### B-M1-01 — Mission and GPS domain foundation

- **Objective:** Define mission lifecycle and consented, batched GPS ingestion against the shared corridor and identity primitives.
- **Owner:** Path B.
- **Dependencies:** A-M1-02, A-M1-03, A-M1-04, S-M0-01.
- **Inputs:** `Mission`, `PositionBatch`, vehicle profiles, consent/retention rules.
- **Outputs:** mission/vehicle/position service over A-owned persistence; replay fixture with labelled synthetic/consented points; schema requests only for later discovered changes.
- **Allowed files:** `src/ner_lens/missions/**`, `src/ner_lens/gps/**`, `tests/path_b/missions/**`, `docs/schema-requests/*`.
- **Forbidden files:** direct edits to `migrations/**`, identity policy, route legality, status transitions, lockfiles.
- **Consumes:** `AuthContext`, `RoadSegment`, mission and position interfaces.
- **Produces:** `create_mission()` and `ingest_position_batch()` services plus DTO inputs/results for Sol-owned endpoint wiring; status `planned|active|paused|delayed|delivered|cancelled`.
- **Acceptance criteria:** only active consented missions collect positions; sequence/idempotency and server receive time are retained; impossible timestamps/order and large jumps are flagged, not silently smoothed; precise traces are not public; mission stays on its graph version unless explicitly recalculated.
- **Tests:** batch idempotency/order tests; consent and authorization matrix; clock skew/teleport fixture; retention visibility test.
- **Validation/integration:** run against A-M1-04 tables; send schema requests only for approved follow-up changes; Sol checks endpoint contract; route task can query mission vehicle profile.
- **Completion condition:** B service passes tests against A's migration contract and replay data is clearly labelled.

#### B-M1-02 — GraphHopper adapter and hard-constraint route interface

- **Objective:** Wrap GraphHopper profiles and alternatives behind a deterministic adapter that enforces physical/legal constraints before risk scoring.
- **Owner:** Path B.
- **Dependencies:** B-M0-01; A-M1-03; S-M0-01.
- **Inputs:** graph checksum/config, `RouteVerificationPolicy`, `light_goods|rigid_truck|emergency`, origin/destination, active closed/restricted segment lookup contract.
- **Outputs:** `route_candidates(request)`, GraphHopper config/fixture, no-feasible-route result, route-edge-to-segment mapping.
- **Allowed files:** `src/ner_lens/routing/**`, `data/corridor/graphhopper/**`, `tests/path_b/routing/**`, `docs/schema-requests/*`.
- **Forbidden files:** Alembic files, status authority rules, model training, public tile service dependency, route closure decisions.
- **Consumes:** `RoadSegment`, `StatusDecision` read interface, `Mission`, graph version.
- **Produces:** route alternatives with distance/time, hard constraints, graph version, unavailable-router/degraded mode.
- **Acceptance criteria:** active applicable closures and verified physical/legal restrictions are excluded; risk alone never hard-excludes; alternatives are limited and inspectable; router outage returns a labelled degraded result; no-feasible-route explains blocking constraints.
- **Tests:** vehicle restriction, closed edge, direction, router outage, graph-version consistency, and all four `RouteVerificationPolicy` outcome tests.
- **Validation/integration:** A supplies status lookup; Sol checks `RouteComparison` envelope; B records route replay for thin slice.
- **Completion condition:** route adapter passes all fixtures and emits canonical `RouteComparison` candidates.

#### S-M1-01 — Shared contract package and API shell

- **Objective:** Publish versioned shared request/response schemas and wire an API shell without owning domain behavior.
- **Owner:** Sol.
- **Dependencies:** S-M0-01; A-M1-01 names; B-M1-01/B-M1-02 interface review.
- **Inputs:** interface registry and compatibility rules.
- **Outputs:** shared contract package, error envelope, endpoint registry, generated OpenAPI only from implemented routes.
- **Allowed files:** `src/ner_lens/contracts/**`, `src/ner_lens/app.py` wiring, `tests/contracts/**`, `docs/openapi/*` when generated by this task.
- **Forbidden files:** domain migrations, lockfile changes before baseline, business logic, source adapters.
- **Consumes:** `AuthContext`, `CorridorVersion`, `Mission`, `RouteComparison` names.
- **Produces:** stable serialization and canonical error codes: `invalid_request|unauthenticated|forbidden|not_found|conflict|idempotency_conflict|payload_too_large|unsupported_media_type|unprocessable_entity|rate_limited|upstream_unavailable|degraded|internal_error`.
- **Acceptance criteria:** JSON/GeoJSON field names and timezone rules are unambiguous; unknown/null semantics are documented; contract tests fail on accidental breaking changes; shell imports without a configured external service.
- **Tests:** contract round-trip tests, OpenAPI schema validation, error-envelope tests.
- **Validation/integration:** A/B run contract tests before merging service tasks; OpenAPI remains a generated artifact, not hand-edited.
- **Completion condition:** shared package is importable and versioned against the baseline.

### M2 — Evidence, status, and the thin operational slice

Outcome: a reviewed status can deterministically change route comparison and be audited, with explicit unknown/stale state. This is the first vertical slice.

#### A-M2-01 — Source snapshots and evidence provenance

- **Objective:** Store immutable source snapshots and normalized evidence with event-time provenance, hashes, quality flags, and review state.
- **Owner:** Path A.
- **Dependencies:** A-M1-01/A-M1-03; S-M1-01; Terra P0.
- **Inputs:** `SourceSnapshot`, `Evidence`, adapter contract, source terms.
- **Outputs:** evidence tables/service and migration; `record_snapshot()`, `record_evidence()`, segment association service.
- **Allowed files:** `src/ner_lens/evidence/**`, `migrations/**` new revision, `tests/path_a/evidence/**`, `data/manifests/**`.
- **Forbidden files:** model training, route scoring, auto-status transitions, unreviewed alert publishing.
- **Consumes:** source adapter payload with `observed_at`, `source_published_at`, `retrieved_at`, geometry, units, hash, parser version.
- **Produces:** provenance-complete `Evidence`; association methods `segment_intersects|within_buffer|manual_review`; freshness/health values.
- **Acceptance criteria:** raw value is retained; missing units/impossible coordinates/future observation times/unparseable timezone quarantine; HTTP 200 with old data is stale; every evidence item resolves to snapshot/hash; spatial association is recorded.
- **Tests:** stale fixture, schema drift quarantine, units/timezone/geometry validation, spatial boundary, immutable snapshot and source correction/supersession tests.
- **Validation/integration:** status task can cite evidence IDs; ingestion task can call service; Sol checks response shape and source health.
- **Completion condition:** evidence fixture can be replayed from snapshot to segment association with no manual edits.

#### A-M2-02 — Review workflow, precedence, and status state machine

- **Objective:** Implement review actions, conflicts, expiry, authority/vehicle scope, and the status state machine with immutable audit events.
- **Owner:** Path A.
- **Dependencies:** A-M2-01; A-M1-02; A-M1-03.
- **Inputs:** evidence precedence; statuses `open|restricted|closed|unknown`; `ReviewAction`, `StatusDecision`.
- **Outputs:** review/status service and migration; `review_evidence()`, `decide_status()`, `get_current_status()`; audit before/after hashes.
- **Allowed files:** `src/ner_lens/evidence/**`, `src/ner_lens/status/**`, `src/ner_lens/audit/**`, `migrations/**` new revision, `tests/path_a/status/**`.
- **Forbidden files:** model-driven transitions, route cost code, frontend-only authorization, arbitrary translation.
- **Consumes:** `Evidence`, `AuthContext`, `ReviewAction`.
- **Produces:** `StatusDecision` and conflict records; expiry transition to `unknown`; precedence resolver preserving lower-ranked evidence.
- **Acceptance criteria:** no model transition exists; weather/risk cannot close; reviewer scope is enforced; disagreement remains visible; vehicle/direction scope is honored; expired closure/open transitions to unknown unless renewed; all actions are audited and idempotent.
- **Tests:** state-machine transition table; precedence/conflict; expiry; vehicle/direction scope; authorization; idempotent review replay.
- **Validation/integration:** B route adapter excludes only applicable closed/incompatible segments; Sol verifies event and error contracts; Terra P1 criteria are prepared.
- **Completion condition:** a reviewed fixture changes current segment status and produces a complete audit trail.

#### B-M2-01 — Transparent risk baseline and route post-score

- **Objective:** Provide a six-hour transparent hazard-rule baseline and a separate route score using risk, uncertainty, staleness, and deadline terms.
- **Owner:** Path B.
- **Dependencies:** A-M1-04; A-M2-01/A-M2-02; B-M1-02; S-M1-01.
- **Inputs:** features available at issue time; current status; route candidates; declared weights; baseline policy.
- **Outputs:** `RiskPrediction(mode=baseline|abstain)`, normalized route score, explanation, feature snapshot manifest.
- **Allowed files:** `src/ner_lens/risk/**`, `src/ner_lens/routing/**`, `tests/path_b/risk/**`, `models/cards/**` baseline card.
- **Forbidden files:** auto-closure, unreviewed evidence mutation, candidate ML promotion, lockfiles.
- **Consumes:** `Evidence`, `StatusDecision`, `RouteComparison`, feature snapshot.
- **Produces:** `calculate_baseline(segment, issue_time)`, `score_route(route, mission)`, route explanations showing time/distance/risk/uncertainty/staleness separately.
- **Acceptance criteria:** risk is probability or `insufficient_evidence`; missingness/staleness is visible and never replaced with zero; weights are normalized and frozen; hard constraints run before score; route recommendation states invalidating evidence; no fabricated metrics.
- **Tests:** monotonic stale penalty; missing-vs-zero; normalization; baseline prevalence/rainfall-rule fixtures; route score explanation and no-feasible-route tests.
- **Validation/integration:** status change causes route recomputation; Sol checks `RiskPrediction`/`RouteComparison`; baseline card records no measured performance until evaluation runs.
- **Completion condition:** replay fixture yields two inspectable alternatives and a deterministic baseline decision.

#### S-M2-01 — Thin-slice API wiring and OpenAPI contract checkpoint

- **Objective:** Wire the first end-to-end flow: evidence replay → reviewed status → route compare → audit response.
- **Owner:** Sol.
- **Dependencies:** A-M2-01/A-M2-02; B-M1-02/B-M2-01; S-M1-01.
- **Inputs:** replay fixtures, `AuthContext`, corridor, evidence, status, route, risk contracts.
- **Outputs:** endpoint wiring for `GET /v1/corridors/{id}/state`, `POST /v1/routes/compare`, `POST /v1/reviews/{evidence_id}`, `POST /v1/status-decisions`; contract test and OpenAPI checkpoint.
- **Allowed files:** `src/ner_lens/app.py`, `src/ner_lens/api/**`, `src/ner_lens/contracts/**`, `tests/integration/thin_slice/**`, `docs/openapi/checkpoints/**`.
- **Forbidden files:** domain internals, Alembic revisions, lockfile changes, direct DB writes bypassing services.
- **Consumes:** all M2 produced interfaces.
- **Produces:** stable request/response envelopes with source age, status, risk mode, route alternatives, graph version, audit reference.
- **Acceptance criteria:** no manual DB edit is needed; a reviewed status deterministically changes affected route output; unknown/stale state is visible; forbidden access returns canonical error; OpenAPI checkpoint is generated from code.
- **Tests:** API integration on disposable PostGIS; replay flow; authorization; OpenAPI schema; route recomputation assertion.
- **Validation/integration:** revalidate the P0 safety invariants; M3 may begin only after this checkpoint is green.
- **Completion condition:** thin-slice replay is green from clean DB and its evidence bundle is stored.

### M3 — Offline protocol, field reports, mission tracking, and alerts skeleton

Outcome: offline capture/sync and GPS mission replay work with duplicates/conflicts preserved; alert emission is deterministic but remains template-governed.

#### A-M3-01 — Idempotent offline field-report protocol and media state

- **Objective:** Implement store-and-forward metadata/media protocol with idempotency, partial-upload handling, clock flags, conflict preservation, and review handoff.
- **Owner:** Path A.
- **Dependencies:** A-M2-01/A-M2-02; S-M2-01.
- **Inputs:** field report lifecycle; `client_report_id`, device sequence, media hash, `AuthContext`.
- **Outputs:** field-report/media tables, migration, sync service/DTO results, and sync state machine for Sol-owned endpoint wiring.
- **Allowed files:** `src/ner_lens/sync/**`, `src/ner_lens/evidence/**`, `migrations/**` new revision, `tests/path_a/sync/**`.
- **Forbidden files:** direct route changes, GPS raw trace policy, client-side-only authorization, lockfiles.
- **Consumes:** `Evidence`, `ReviewAction`, idempotency primitive, media metadata.
- **Produces:** states `saved_on_device|metadata_synced|media_incomplete|ready_for_review|accepted|rejected|conflict`; canonical ID response.
- **Acceptance criteria:** same client ID is idempotent; same media hash reuses protected object without merging reports; disagreements create conflict; metadata can sync while media fails; app-visible state never says submitted before server acknowledgement; token expiry preserves queue.
- **Tests:** repeated metadata replay; duplicate media; partial media; clock skew; conflict; oversized/malformed upload; auth revocation; restart persistence fixture.
- **Validation/integration:** Sol maps error/state contracts; B can attach accepted evidence to mission route impact; A's migration up/down passes.
- **Completion condition:** controlled offline protocol test loses zero accepted records and creates zero duplicate canonical records.

#### A-M3-02 — Media quarantine and scan boundary

- **Objective:** Prevent untrusted upload bytes from becoming reviewable or retrievable before deterministic validation and an approved scan result.
- **Owner:** Path A.
- **Dependencies:** A-M3-01; S-M1-01 media contract.
- **Inputs:** upload bytes/headers, configured type and size limits, `ObjectStore`, `MediaScanner`, media state contract.
- **Outputs:** quarantine storage flow, server-computed SHA-256, decode/type/size validation, scan-result transition service, and local test adapters.
- **Allowed files:** `src/ner_lens/sync/**`, `src/ner_lens/evidence/**`, `src/ner_lens/media/**`, `tests/path_a/media/**`, `migrations/**` corrective revision only if approved.
- **Forbidden files:** public media serving, production-specific storage/scanner dependency, Path B modules, application wiring, lockfiles.
- **Consumes:** `ObjectStore`, `MediaScanner`, media object and idempotency contracts.
- **Produces:** `pending -> clean|rejected|error` scan transitions; protected storage reference; retrieval eligibility only for `clean` objects.
- **Acceptance criteria:** client hashes are never trusted without recomputation; content type must agree with successful decode; oversized, malformed, polyglot, decompression-bomb and traversal fixtures are rejected/quarantined; pending/rejected/error media cannot be retrieved or used to approve complete evidence.
- **Tests:** hash mismatch, size limit, MIME/decode mismatch, polyglot, decompression bomb, traversal filename, scanner timeout/failure, and clean transition tests.
- **Validation/integration:** Sol wires upload responses only after this task; Terra reviews quarantine ACL and bypass attempts; no local test scanner supports a production-clean claim.
- **Completion condition:** every malicious fixture remains unavailable and a clean fixture becomes eligible exactly once with an audit event.

#### B-M3-01 — GPS replay, ETA baseline, and mission state

- **Objective:** Replay a consented/synthetic-labelled trace through an active mission, detect anomalies, and expose a baseline ETA interval.
- **Owner:** Path B.
- **Dependencies:** B-M1-01; B-M2-01; S-M2-01.
- **Inputs:** `Mission`, `PositionBatch`, graph version, route alternative, labelled replay trace.
- **Outputs:** mission progress projection, last-fix age, ETA baseline and anomaly flags.
- **Allowed files:** `src/ner_lens/missions/**`, `src/ner_lens/gps/**`, `tests/path_b/gps/**`, `tests/replay/gps/**`.
- **Forbidden files:** real personal traces without consent, migration files, status authority, public precise positions.
- **Consumes:** `PositionBatch`, `RouteComparison`, `RiskPrediction` read interface.
- **Produces:** mission progress and `ETAEstimate(mode=baseline, interval, caveat)`; anomaly states `clock_skew|teleport|out_of_order|stale_fix`.
- **Acceptance criteria:** collection only for active consented missions; original points preserved; snap-to-road is visualization-only; large jumps/out-of-order points are flagged; mission end stops collection; no trace is implied current when stale.
- **Tests:** sequence/idempotency; anomaly detection; stale last fix; route graph-version lock; ETA interval caveat; mission completion.
- **Validation/integration:** Sol checks mission/GPS API; alerts can use stale-fix and delay facts; no claim of live GPS if fixture is replay.
- **Completion condition:** labelled replay updates mission and ETA without leaking precise trace outside authorized scope.

#### B-M3-02 — Deterministic alert rules and reviewed templates

- **Objective:** Generate deduplicated persisted in-app alerts from reviewed status, stale critical feeds, route risk, or mission delay using approved English/Assamese templates. Streaming is an additive later interface.
- **Owner:** Path B.
- **Dependencies:** A-M1-04; A-M2-02; A-M3-01; B-M3-01; S-M1-01.
- **Inputs:** `StatusDecision`, `RiskPrediction`, mission/ETA, source health, reviewed templates.
- **Outputs:** alert service, template registry/version, cursor-query DTO results, and delivery/ack state for Sol-owned endpoint wiring.
- **Allowed files:** `src/ner_lens/alerts/**`, `data/templates/**`, `tests/path_b/alerts/**`, `docs/decisions/alert-policy.md`.
- **Forbidden files:** unconstrained LLM translation, automatic closure, recipient bypass, migrations (request A), unreviewed Bengali/operational copy.
- **Consumes:** `Alert`, status/risk/mission/source-health interfaces.
- **Produces:** deterministic `dedupe_key`, severity, audience, language, variables, delivery receipt and acknowledgement.
- **Acceptance criteria:** repeated ingest does not repeat alerts; severity increase is not suppressed by prior acknowledgement; stale/failed feed alerts say degraded; templates preserve road IDs, times, numbers, and contact instructions; alert authorization is enforced.
- **Tests:** dedupe/material-change; severity escalation; bilingual snapshot; recipient scope; cursor replay; stale-feed and no-feasible-route fixtures.
- **Validation/integration:** Sol checks alert-list schema; A verifies status evidence references; M6 release includes approved template evidence.
- **Completion condition:** one reviewed status change emits one localized, auditable alert with no duplicate on replay.

#### S-M3-01 — Offline sync contract and backend replay harness

- **Objective:** Publish client-facing sync contracts and a backend replay harness for reconnect, reauthentication, media retry, duplicate requests, conflicts, and alert retrieval. Browser persistence remains a separate client responsibility.
- **Owner:** Sol.
- **Dependencies:** A-M3-01/A-M3-02; B-M3-01/B-M3-02; S-M2-01.
- **Inputs:** sync/mission/alert states and error envelopes.
- **Outputs:** OpenAPI/JSON fixtures, integration harness, and an offline-client scenario contract.
- **Allowed files:** `src/ner_lens/contracts/**`, `tests/integration/offline_protocol/**`, `docs/openapi/checkpoints/**`.
- **Forbidden files:** domain migrations, server business logic, source adapter implementation, lockfile changes before baseline approval.
- **Consumes:** field report, position, alert and route contracts.
- **Produces:** server states `accepted_for_review|media_incomplete|conflict|synced` and stable replay responses for a future client.
- **Acceptance criteria:** duplicate requests cannot lose or duplicate accepted records; expired authentication rejects protected sync without changing canonical state; partial media and report conflicts remain visible; replay/simulation is labelled.
- **Tests:** pytest/httpx integration tests for reauthentication, partial media, duplicate body, conflicting body, and cursor-based alert retrieval.
- **Validation/integration:** The backend protocol passes against frozen client fixtures; no browser or accessibility completion claim is made in this repository.
- **Completion condition:** every offline-client server transition has a deterministic request/response fixture and passing backend integration test.

### M4 — Ingestion, feature snapshots, and risk baseline evaluation

Outcome: permitted source adapters replay safely, features are leakage-safe, and the transparent baseline is evaluated before any candidate ML work.

#### A-M4-01 — Source adapter framework and immutable ingestion jobs

- **Objective:** Implement scheduled, fail-closed source adapters for permitted replay/public sources and a common snapshot/normalization pipeline.
- **Owner:** Path A.
- **Dependencies:** A-M2-01; A-M3-01; S-M1-01.
- **Inputs:** adapter contract; IMD/GSI/CWC/ASDMA/SACHET source manifests; permitted fixtures; timeout/cadence/terms.
- **Outputs:** `SourceAdapter.fetch()`, `normalize()`, `validate()`, `persist_snapshot()`; Typer ingestion command; source health records.
- **Allowed files:** `src/ner_lens/ingestion/**`, `src/ner_lens/evidence/**`, `data/manifests/**`, `tests/path_a/ingestion/**`, `migrations/**` new revision.
- **Forbidden files:** unauthorized scraping, raw credentials, automatic status publication, model code, lockfiles.
- **Consumes:** `SourceSnapshot`, `Evidence`, source manifest and terms.
- **Produces:** immutable raw snapshot/hash, normalized staging/evidence, health `healthy|stale|failed|quarantined`, run ID.
- **Acceptance criteria:** timeout/client identity/cadence are enforced; schema drift and unsafe redirects quarantine; HTTP success with old content is stale; failed feed is not “no hazard”; exact response/file and metadata are retained; parser version is recorded.
- **Tests:** recorded fixture per source; schema-change; stale 200; unsafe URL/redirect; unit/timezone/geometry; retry/idempotency; source health transitions.
- **Validation/integration:** status/risk consume only normalized evidence; Terra reviewer confirms terms; no live claim if only replay fixture exists.
- **Completion condition:** all selected adapters pass fixtures and a repeat run creates no duplicate snapshots/evidence.

#### A-M4-02 — Feature snapshot construction and label ledger

- **Objective:** Build versioned segment×issue-time×six-hour feature snapshots and auditable labels without treating unreported hours as negatives.
- **Owner:** Path A.
- **Dependencies:** A-M4-01; A-M1-03; A-M2-02.
- **Inputs:** source snapshots/evidence; static corridor features; accepted event/observation ledger; dataset manifest schema.
- **Outputs:** Parquet feature/label snapshots and SHA-256 manifests; label classes `disrupted|not_disrupted_observed|unknown|ambiguous`; leakage report.
- **Allowed files:** `src/ner_lens/features/**`, `data/manifests/**`, `models/cards/**` dataset card, `tests/path_a/features/**`, `tests/replay/labels/**`.
- **Forbidden files:** model promotion, synthetic results as validation, random point split, future source values.
- **Consumes:** `Evidence`, `StatusDecision`, source health and segment geometry.
- **Produces:** feature fields with value/source_time/age/missing/quality/fallback; dataset ID, cutoff, source hashes, row/positive/unknown counts.
- **Acceptance criteria:** event/published/retrieved/reviewed times are separated; post-issue data cannot enter features; event groups remain in one fold; latest season can be held out; weak negatives are labelled and sensitivity-tested; unknown/ambiguous are not silently negative.
- **Tests:** cutoff/leakage; event grouping; missing-vs-zero; manifest hash; weak-negative exclusion; deterministic seed.
- **Validation/integration:** B receives only manifest-addressed snapshots; Sol exposes dataset/model metadata shape; no accuracy claim before evaluation.
- **Completion condition:** one immutable dataset manifest and passing leakage report exist.

#### B-M4-01 — Baseline evaluation and model card

- **Objective:** Evaluate prevalence and transparent hazard-rule baselines with blocked temporal/event-grouped validation and publish honest metrics.
- **Owner:** Path B.
- **Dependencies:** A-M4-02; B-M2-01.
- **Inputs:** immutable feature/label manifest; baseline definitions; declared threshold and bootstrap policy.
- **Outputs:** evaluation JSON, PR-AUC/Brier/calibration/recall/precision/lead-time report, baseline model card, failure slices.
- **Allowed files:** `src/ner_lens/risk/**`, `models/cards/**`, `tests/path_b/model/**`, `data/manifests/**` result manifests.
- **Forbidden files:** candidate promotion, random split, invented values, replacing operational baseline before gate.
- **Consumes:** `RiskPrediction`, dataset manifest.
- **Produces:** `GET /v1/models/current` baseline card with cutoff, metrics or `not measured`, scope, known limits, abstention rules.
- **Acceptance criteria:** prevalence row is included; test season is untouched; event-group bootstrap intervals accompany metrics; metrics slice by band/season/event type/freshness; no paper score is reused; baseline remains active if labels are insufficient.
- **Tests:** deterministic evaluation seed; blocked split; metric/report schema; calibration; baseline regression fixture.
- **Validation/integration:** Sol updates contract only through schema request; Terra reviews whether ML promotion remains conditional.
- **Completion condition:** baseline evaluation artifact is reproducible or explicitly reports demonstration-only insufficiency.

#### S-M4-01 — Ingestion/risk integration and data-health surface

- **Objective:** Expose source run status, dataset/model metadata, and degraded-mode behavior through backend API contracts.
- **Owner:** Sol.
- **Dependencies:** A-M4-01/A-M4-02; B-M4-01.
- **Inputs:** source health, feature manifest, baseline card, risk output.
- **Outputs:** `GET /health/sources`, `GET /v1/models/current`, integration tests and OpenAPI checkpoint.
- **Allowed files:** `src/ner_lens/api/**`, `src/ner_lens/contracts/**`, `tests/integration/data_health/**`, `docs/openapi/checkpoints/**`.
- **Forbidden files:** adapter internals, feature calculations, migrations, unreviewed copy.
- **Consumes:** `SourceSnapshot.health`, dataset/model cards, `RiskPrediction`.
- **Produces:** API state that distinguishes healthy/stale/failed/quarantined and baseline/abstain.
- **Acceptance criteria:** feed failure lowers confidence or abstains; model artifact failure falls back to transparent baseline; every risk shows source age/model version/feature snapshot; no stale green state persists indefinitely.
- **Tests:** integration fixtures for each degraded state; model artifact failure; health endpoint contract; accessibility text alternative.
- **Validation/integration:** cross-module test confirms ingestion affects only affected segment-horizons and route output; OpenAPI snapshot is generated.
- **Completion condition:** data-health scenario passes with no manual DB mutation.

### M5 — Conditional ML, route quality, and operational completeness

Outcome: candidate ML exists only if it beats the baseline under the declared gate; routing, alerts, and mission evidence are complete.

#### B-M5-01 — Conditional candidate model and promotion gate

- **Objective:** Train/evaluate logistic regression first, then histogram gradient boosting only if the blocked test and calibration gate justify it.
- **Owner:** Path B.
- **Dependencies:** B-M4-01; A-M4-02; S-M4-01.
- **Inputs:** immutable dataset; model ladder; promotion thresholds ratified by operational owner; feature schema checksum.
- **Outputs:** candidate artifact(s), model card, evaluation comparison, promotion decision or baseline retention.
- **Allowed files:** `src/ner_lens/risk/**`, `models/cards/**`, `models/artifacts/**` labelled artifacts, `tests/path_b/model/**`.
- **Forbidden files:** automatic promotion, untracked feature changes, closure status writes, fabricated results, unreviewed thresholds.
- **Consumes:** `RiskPrediction`, feature manifest and baseline metrics.
- **Produces:** model mode `candidate` only after gate; otherwise `baseline`; explanation with association not causation; abstention on OOD/stale/schema failure.
- **Acceptance criteria:** positive Brier skill vs baseline on untouched test; PR-AUC exceeds prevalence and baseline; calibration and high-risk recall/false-alert requirements pass; slices and weak-label sensitivity are reported; fewer than 30 positive event groups is demonstration-only; rollback points to baseline.
- **Tests:** event-group forward split; calibration; feature cutoff; artifact checksum; OOD/abstain; fallback; deterministic seed.
- **Validation/integration:** Terra P1 reviews promotion; Sol exposes model mode and card; route scorer treats candidate output as risk, never status.
- **Completion condition:** signed promotion decision exists; active mode is explicitly baseline if any criterion fails.

#### B-M5-02 — Risk-aware route ranking and route-quality metrics

- **Objective:** Complete Pareto-aware route ranking, hysteresis, route explanations, and replay metrics without hiding trade-offs in one score.
- **Owner:** Path B.
- **Dependencies:** A-M1-04; B-M1-02; B-M2-01; B-M5-01; A-M2-02.
- **Inputs:** feasible GraphHopper candidates, status decisions, predictions, source freshness, mission deadline, frozen weights.
- **Outputs:** route ranking service, route decision log, metrics for unsafe recommendation, avoidable exposure, regret, churn, latency, override.
- **Allowed files:** `src/ner_lens/routing/**`, `src/ner_lens/risk/**`, `tests/path_b/routing/**`, `models/cards/**` route policy.
- **Forbidden files:** changing legality based on risk, silent weight changes, route graph mutation mid-mission, consumer navigation scope.
- **Consumes:** `RouteComparison`, `StatusDecision`, `RiskPrediction`, `Mission`.
- **Produces:** `RouteAlternative` with time/distance/risk/uncertainty/staleness/evidence and material-change reason, plus an immutable persisted route decision referencing policy ID/version.
- **Acceptance criteria:** zero applicable closure/physical restriction violations in replay; no route churn without material input/policy change; no-feasible-route and deadline infeasibility are honest; graph and policy versions are shown; baseline ETA is labelled until validated; a stored comparison can be reproduced from its frozen references.
- **Tests:** hard-constraint replay; all four policy outcomes; policy-version reproducibility; persisted decision restore/replay; hysteresis; route explanation completeness; latency p95 fixture; graph-version consistency; operator override reason.
- **Validation/integration:** M3 alert on route material change; S-M6 cross tests consume metrics; Terra P1 route gate.
- **Completion condition:** route replay meets all declared engineering gates or release is blocked.

#### B-M5-03 — Mission/alert operational integration

- **Objective:** Connect reviewed status/risk changes to affected active missions, GPS progress, alert rules, and acknowledgement without leaking precise traces.
- **Owner:** Path B.
- **Dependencies:** B-M3-01/B-M3-02; B-M5-02; A-M2-02/A-M3-01.
- **Inputs:** active missions, route decisions, status/evidence changes, stale sources, approved templates.
- **Outputs:** mission impact projection, alert delivery receipts, operator override/audit views.
- **Allowed files:** `src/ner_lens/missions/**`, `src/ner_lens/alerts/**`, `tests/path_b/operational/**`, `data/templates/**`.
- **Forbidden files:** status approval, direct migration edits, unconstrained translation, public precise GPS.
- **Consumes:** `Mission`, `PositionBatch`, `StatusDecision`, `RouteComparison`, `Alert`.
- **Produces:** affected-mission list, recomputed route request, localized alert, last-fix/ETA state, audit references.
- **Acceptance criteria:** status approval is the trigger for closure consequences; risk-only change can notify but not close; mission graph version is stable unless operator recalculates; driver/public views are scope-limited; alert dedupe/ack semantics hold.
- **Tests:** end-to-end mission impact; risk-only vs status change; stale GPS; template/recipient scope; acknowledgement escalation.
- **Validation/integration:** Sol cross-module suite; P1 evidence bundle includes alert and mission audit.
- **Completion condition:** one mission follows status change → route recomputation → localized alert → replayed progress without manual edits.

#### S-M5-01 — Dependency/lock changes and shared backend wiring

- **Objective:** Add only justified backend dependencies after the baseline is green, update the Python lockfile reproducibly, and wire shared API surfaces.
- **Owner:** Sol.
- **Dependencies:** M1 baseline; A/B M4 contracts; explicit dependency requests.
- **Inputs:** existing environment contract; approved dependency request with reason, license, version, security impact, rollback.
- **Outputs:** `uv.lock` or equivalent changes, API wiring, dependency manifest, and OpenAPI checkpoint.
- **Allowed files:** `uv.lock` or equivalent, `pyproject.toml`, `src/ner_lens/app.py`, `src/ner_lens/contracts/**`, `tests/contracts/**`, `docs/openapi/**`.
- **Forbidden files:** dependency edits before baseline, speculative packages, Alembic, domain implementations, secrets.
- **Consumes:** interface contracts and approved requests.
- **Produces:** reproducible install and shared wiring for route/state/mission/evidence/alerts.
- **Acceptance criteria:** every added package is necessary and pinned; no duplicate capability exists; clean install/checks pass; the lockfile diff is reviewable; shared API responses preserve stale, unknown, and non-map-readable state.
- **Tests:** clean install verification; lint/type/import; contract tests; dependency audit.
- **Validation/integration:** A/B verify no transitive API mismatch; OpenAPI snapshot is generated from code.
- **Completion condition:** lockfiles and shared wiring merge only after the baseline and dependency review pass.

### M6 — Hardening, Terra P1, and release

Outcome: replayable release with migrations, security/accessibility/resilience evidence, honest claims, and rollback.

#### A-M6-01 — Path A hardening, migration verification, provenance, and restore

- **Objective:** Harden authorization/provenance/sync/ingestion paths, verify every Alembic chain, and prove backup/restore without data loss.
- **Owner:** Path A.
- **Dependencies:** all A tasks; B/S integration checkpoints.
- **Inputs:** release candidate; migration history; audit/event fixtures; backup policy; security controls.
- **Outputs:** migration/release report, restore transcript, authorization matrix report, provenance report, source terms bundle.
- **Allowed files:** `src/ner_lens/identity/**`, `src/ner_lens/security/**`, `src/ner_lens/corridor/**`, `src/ner_lens/evidence/**`, `src/ner_lens/status/**`, `src/ner_lens/audit/**`, `src/ner_lens/media/**`, `src/ner_lens/persistence/**`, `src/ner_lens/ingestion/**`, `src/ner_lens/features/**`, `src/ner_lens/sync/**`, A-owned common utilities, `migrations/**` new corrective revisions, `ops/scripts/**`, `ops/backups/**`, `tests/path_a/**`, and A-owned `docs/release/**` evidence.
- **Forbidden files:** destructive production reset, disabling audit, downgrading production without approval, secrets, unrelated B/S internals.
- **Consumes:** all shared contracts and release candidate.
- **Produces:** verified `/health/live|ready|sources`, restore command, audit trail and migration checksum manifest.
- **Acceptance criteria:** clean upgrade and disposable downgrade; restore-tested backup; object/function authorization passes; malicious/oversized media and unsafe source URL tests pass; provenance reconstructs every status, route policy/decision, alert and model input; no secrets/full GPS in logs.
- **Tests:** full Path A suite; migration up/down; security fixtures; restore smoke including policy-versioned route decision; stale/failure/quarantine; offline loss/duplicate.
- **Validation/integration:** Terra P1 review; B/S release suites consume report; rollback plan is executable.
- **Completion condition:** Path A signs P1 readiness or records a blocking defect and retains the last green baseline.

#### B-M6-01 — Path B resilience, performance, and operational demo bundle

- **Objective:** Verify mission/GPS/routing/risk/alerts under router/model/feed failure, declared load, and normal/degraded/no-feasible-route stories.
- **Owner:** Path B.
- **Dependencies:** all B tasks; A-M6-01 interfaces; S-M5-01.
- **Inputs:** frozen graph/data/model/replay artifacts; performance hardware declaration; alert/template approvals.
- **Outputs:** Path B test report, route/risk/alert demo replay, performance metrics, model card and known-failure list.
- **Allowed files:** B-owned modules/tests, `models/cards/**`, `tests/replay/**`, `docs/release/**`.
- **Forbidden files:** changing baseline/model gate after seeing final test; claiming live GPS/integration; migration edits; closure automation.
- **Consumes:** `RouteComparison`, `RiskPrediction`, `Mission`, `Alert`, source health.
- **Produces:** deterministic release scenarios and labelled replay evidence.
- **Acceptance criteria:** router unavailable/model artifact unavailable/feed stale cases degrade honestly; p95 route/API targets are measured on declared hardware; all routes show graph version/evidence time/trade-offs; zero unsafe recommendation in replay; bilingual alert is reviewed; candidate ML is disabled if P1 gate fails.
- **Tests:** full Path B suite; resilience/property/security/accessibility/latency; replay smoke; no-feasible-route; GPS stale/jump; alert dedupe.
- **Validation/integration:** Terra P1 validates safety and claims; Sol bundles OpenAPI and cross-module evidence.
- **Completion condition:** Path B signs release evidence or reverts to baseline/degraded mode.

#### S-M6-01 — Cross-module tests, OpenAPI snapshot, and release assembly

- **Objective:** Run the smallest complete backend gate and assemble a truthful replay-capable release evidence bundle.
- **Owner:** Sol.
- **Dependencies:** A-M6-01; B-M6-01; S-M5-01.
- **Inputs:** clean release candidate, all task reports, source/graph/model manifests, dependency locks.
- **Outputs:** frozen OpenAPI snapshot; cross-module tests; SBOM/lockfile bundle; demo dataset labels; release checklist and rollback pointer.
- **Allowed files:** `tests/integration/**`, `tests/e2e/**`, `docs/openapi/**`, `docs/release/**`, release metadata.
- **Forbidden files:** silently fixing domain code during assembly, migration edits, unreviewed copy, unlabelled data.
- **Consumes:** all interfaces and reports.
- **Produces:** gate sequence `format/lint → type checks → unit/property → migration → source contracts → leakage/evaluation → API/PostGIS/GraphHopper → sync protocol → auth → health/replay`.
- **Acceptance criteria:** OpenAPI matches runtime; all official capabilities are working/replayed/simulated or mapped to a named dependency; no manual DB edits; source/time/confidence are visible; normal, degraded, no-feasible-route, and sync stories run from frozen fixtures; client-only offline/accessibility evidence is labelled external; Terra P1 sign-off is recorded.
- **Tests:** full cross-module pytest suite; contract drift; clean checkout; release replay smoke.
- **Validation/integration:** merge only after A/B sign-off; tag release and preserve previous passing tag for rollback.
- **Completion condition:** release candidate passes Terra P1 and the evidence bundle is complete; otherwise release is blocked and last green baseline remains active.

## Required completion order

1. M0 tasks and Terra P0.
2. A-M1-01 → A-M1-02/A-M1-03/A-M1-04; S-M1-01; then B-M1-01/B-M1-02.
3. A-M2-01 → A-M2-02; B-M2-01; S-M2-01 thin slice.
4. A-M3-01 → A-M3-02 and B-M3-01/B-M3-02; S-M3-01.
5. A-M4-01 → A-M4-02; B-M4-01; S-M4-01.
6. B-M5-01 → B-M5-02 → B-M5-03; S-M5-01 only after baseline lock.
7. A-M6-01 and B-M6-01; S-M6-01; Terra P1; release tag.

Parallel work is allowed only where dependencies and file ownership permit it. Any contract or schema change follows `docs/PARALLEL_EXECUTION_PLAN.md`.



