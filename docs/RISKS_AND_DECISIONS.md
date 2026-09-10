# NER LENS risks and architecture decisions

**Status:** First-run decision log  
**Rule:** Reopen a decision only when new evidence invalidates its recorded context or consequence.

## 1. Contradictions and resolved interpretations

| ID | Conflict | Resolution | Consequence |
|---|---|---|---|
| C-01 | The dossier presents corridor selection as an audit outcome and mentions Guwahati–Aizawl; the technical blueprint selects Guwahati–Silchar. | Guwahati–Silchar is the provisional prototype corridor. Sprint 0 must accept or replace it using route, source, label, and partner evidence. | Do not hard-code corridor-specific domain contracts. Seed data and manifests remain replaceable. |
| C-02 | The blueprint proposes a monorepo with a web app; the project owner identifies this repository as the backend repository. | This repository is backend-only. It exposes client contracts but does not implement React, IndexedDB, Workbox, MapLibre, or client accessibility. | Client E2E and controlled offline-device evidence require a separate client integration later. |
| C-03 | The full-system blueprint lists four containers including `web`, while a local OIDC realm would add another service. | Backend development uses API, PostGIS, and the routing sidecar. Authentication uses a verifier port and test issuer. The deployed identity provider is external. | No local identity platform is added during M0. Full product container count depends on the separate client deployment. |
| C-04 | SIH asks for real-time monitoring; identified sources have different cadence and some are manual. | “Real time” means the latest permitted observation with source time, retrieval time, expected cadence, maximum usable age, health, and visible stale/unknown behavior. | No universal real-time or live-road-closure claim is allowed. |
| C-05 | SIH names roads and bridges; the blueprint centers on road segments. | `RoadSegment` includes `segment_type=road|bridge|tunnel|approach` with direction, physical constraints, authority, and validity. | No separate asset service is needed for the prototype, but bridge-specific constraints remain expressible. |
| C-06 | The model target mentions verified evidence and could learn reporting coverage rather than disruption. | The primary target is a verified operational disruption whose physical occurrence window begins within six hours. Publication, retrieval, and verification times remain separate. Ambiguous occurrence time is excluded from the primary model. | Observation/reporting bias must be measured and disclosed; baseline remains authoritative until promotion. |
| C-07 | Multilingual automated alerts are required, but external SMS/email access is unconfirmed. | The backend persists in-app alerts using human-reviewed English and Assamese templates. External channels use an adapter and remain partner-dependent. | The hackathon can demonstrate automated alert creation without claiming an unapproved telecom integration. |
| C-08 | “Immutable audit” is proposed in a mutable relational database. | The application uses append-only audit events, restricted database permissions, hashes, backups, and reconstruction tests. | Documentation must say append-only/tamper-evident controls, not claim cryptographic immutability. |

## 2. Architecture decision records

### D-001: Backend-only repository

- **Context:** The repository is explicitly identified as backend and is empty.
- **Decision:** Keep frontend implementation outside this repository.
- **Alternatives:** Full monorepo; backend plus minimal demo HTML.
- **Reason:** Prevent scope and ownership ambiguity while preserving API support for a future PWA.
- **Consequences:** Browser offline storage, map accessibility, and service-worker behavior cannot be completed or validated here alone.
- **Affected paths:** Both.
- **Affected contracts:** HTTP, OpenAPI, sync, media, alert polling/streaming.

### D-002: Domain-sliced modular monolith

- **Context:** The complete workflow needs transactional status and audit behavior, but prototype scale is unknown.
- **Decision:** Use one FastAPI process and one PostGIS database with domain package boundaries. Keep GraphHopper external.
- **Alternatives:** Layered monolith; microservices.
- **Reason:** Domain slices support file ownership without distributed transactions or infrastructure overhead.
- **Consequences:** Import boundaries and shared wiring need tests. Services split only after measured load or ownership pressure.
- **Affected paths:** Both.
- **Affected contracts:** All internal/public contracts.

### D-003: Central migration ownership

- **Context:** Parallel Alembic generation creates conflicting heads and schema drift.
- **Decision:** Path A exclusively owns model registry and migrations. Path B submits schema-change requests through Sol.
- **Alternatives:** Per-path migration heads; Sol writes all schemas.
- **Reason:** One ordered schema history is safer than concurrent autogeneration.
- **Consequences:** Path B schema work waits for an approved migration synchronization point.
- **Affected paths:** Both.
- **Affected contracts:** Database schema, fixtures, OpenAPI persistence assumptions.

### D-004: Operational status is human-authorized

- **Context:** Hazard, model, and public reports cannot prove current passability.
- **Decision:** Reviewers may accept evidence, but only a scoped `district_officer` or explicitly configured authority may publish or expire a status decision. Models expose risk only.
- **Alternatives:** Threshold-generated closure; crowd-majority status.
- **Reason:** Prevent unsafe automatic status assertions.
- **Consequences:** Reviewer availability and expiry policy are core operational dependencies.
- **Affected paths:** Path A produces status; Path B consumes it.
- **Affected contracts:** Evidence, review, status, route exclusion, alert trigger.

### D-005: Explicit unknown and expiry

- **Context:** Stale green status is more dangerous than visible uncertainty.
- **Decision:** Expired status resolves to `unknown`. Absence of reports never creates `open` or a negative ML label.
- **Alternatives:** Last-known status indefinitely; optimistic reopening.
- **Reason:** Evidence age must constrain operational confidence.
- **Consequences:** Source freshness and status expiry are required in every relevant read model.
- **Affected paths:** Both.
- **Affected contracts:** Resolved state, routes, alerts, features.

### D-006: Baseline-first AI

- **Context:** No NER LENS dataset or measured model result exists.
- **Decision:** Implement prevalence and transparent hazard-rule baselines before logistic regression. Gradient boosting is conditional. No LLM, RAG, CV, or agent runtime is in the backend prototype.
- **Alternatives:** Deep model first; static susceptibility only; LLM-assisted decision agent.
- **Reason:** Data and calibration, not model capacity, are the likely constraint.
- **Consequences:** M4 may legitimately close with the baseline retained.
- **Affected paths:** Path B implementation, Path A data manifests.
- **Affected contracts:** Risk result, feature cutoff, model metadata, evaluation report.

### D-007: Deterministic feasible routing before risk ranking

- **Context:** A risk score cannot override law, vehicle limits, or confirmed closure.
- **Decision:** Graph/vehicle/status constraints generate feasible alternatives first. Risk, staleness, uncertainty, and deadline penalties rank remaining alternatives transparently.
- **Alternatives:** Single opaque route score; model-driven edge removal.
- **Reason:** Hard safety/legality and soft forecast trade-offs have different authority.
- **Consequences:** Route responses expose components and may return no feasible route.
- **Affected paths:** Path B consumes Path A state.
- **Affected contracts:** Vehicle profile, segment scope, route alternatives, recommendation.

### D-008: Replay-first integrations

- **Context:** Public portals may change and restricted integrations require approval.
- **Decision:** CI and the jury demo use permitted, hashed replay fixtures. Live adapters are added only after access and terms validation.
- **Alternatives:** Live-only demo; unauthorized scraping.
- **Reason:** Reproducibility and lawful access outweigh demo theatre.
- **Consequences:** Every replay response contains mode and provenance labels.
- **Affected paths:** Path A ingestion; Path B GPS/router fixtures.
- **Affected contracts:** Source adapter, snapshot, integration health.

### D-009: No queue or cache in the first slice

- **Context:** Source cadence and prototype load do not justify Kafka, Celery, Redis, or a cache cluster.
- **Decision:** Run scheduled ingestion as short-lived commands. Use database state and HTTP conditional requests. Add a durable queue or cache only after a measured need.
- **Alternatives:** Celery/Redis; Kafka; in-memory shared cache.
- **Reason:** Fewer moving parts and clearer failure recovery.
- **Consequences:** External calls run after transaction commit; periodic work must be idempotent.
- **Affected paths:** Both.
- **Affected contracts:** Jobs, affected-work markers, alerts, health.

### D-010: Runtime compatibility gate

- **Context:** The blueprint selects Python 3.13 and PostgreSQL 17/PostGIS, while native geospatial packages can introduce compatibility risk.
- **Decision:** M0 attempts the blueprint targets without the heavy raster stack. If a reproducible lock cannot be produced, Sol records an evidence-backed fallback before implementation continues.
- **Alternatives:** Pre-emptively downgrade; install the complete GDAL/Rasterio/GeoPandas stack in the API.
- **Reason:** Respect the approved blueprint while avoiding unused native dependencies.
- **Consequences:** Shapely/PyProj or PostGIS cover early geometry needs; raster tooling enters only with a specific ingestion task.
- **Affected paths:** Path A baseline; both consumers.
- **Affected contracts:** Lockfile, container images, CI matrix.

### D-011: Storage and scan ports only at real boundaries

- **Context:** Demo storage is local, production storage and malware scanning are deployment-specific.
- **Decision:** Define `ObjectStore` and `MediaScanner` ports. Keep uploaded media quarantined until an approved scanner returns clean. Use test adapters locally.
- **Alternatives:** S3-specific domain code; accept files without scan state; run a scanner service from day one.
- **Reason:** Security state is mandatory, but infrastructure choice is not yet known.
- **Consequences:** A local test scanner never supports a production-clean claim.
- **Affected paths:** Path A.
- **Affected contracts:** Media object, scan result, storage reference, release configuration.

### D-012: Persisted alerts before streaming

- **Context:** SSE is useful but not required to prove alert correctness.
- **Decision:** Build persisted, deduplicated alerts and polling first. Add SSE only after the alert state machine and authorization pass.
- **Alternatives:** SSE first; external broker.
- **Reason:** Correct durable state is the smaller dependency.
- **Consequences:** API contracts reserve cursor-based retrieval; streaming remains an additive interface.
- **Affected paths:** Path B and Sol wiring.
- **Affected contracts:** Alert list, cursor, acknowledgement, optional stream.

## 3. Risk register

| ID | Severity | Risk | Trigger or evidence | Mitigation | Owner | Gate |
|---|---|---|---|---|---|---|
| R-01 | P0 | Hazard or model mutates operational status | Any automated status transition | Separate contracts, permissions, import test, invariant test | Sol / both | M1–M5 |
| R-02 | P0 | Broken object authorization exposes mission or GPS data | Cross-scope API access succeeds | Deny-by-default policy and authorization matrix | Path A + B | M2–M5 |
| R-03 | P0 | Recommended route contains an applicable closure | Replay or field case reproduces it | Hard constraint before scoring; release stop | Path B | M1–M6 |
| R-04 | P0 | Offline/server replay loses or duplicates accepted evidence | Controlled replay mismatch | Idempotency ledger, request hash, atomic canonical write | Path A | M2–M6 |
| R-05 | P1 | Stale `open` status persists | Decision remains effective after expiry | Resolver computes validity at read time; expiry tests | Path A | M1 |
| R-06 | P1 | OSM lacks heavy-vehicle or structure restrictions | Local audit finds missing limits | Provisional corridor gate, reviewed overrides, visible coverage | Sol / Path A | M0/M6 |
| R-07 | P1 | Prediction learns reporting coverage | Performance collapses by source coverage | Occurrence/observation separation, slice analysis, baseline fallback | Path B | M4 |
| R-08 | P1 | Temporal or spatial leakage inflates model performance | Random split or post-event feature detected | Event-grouped forward holdout and feature-cutoff tests | Both | M4 |
| R-09 | P1 | Untrusted source or URL compromises ingestion | Redirect/private-host or malicious payload | Egress allowlist, redirect validation, size/schema limits | Path A | M3 |
| R-10 | P1 | Malicious media reaches consumers | Unsafe file marked clean or served | Quarantine, type/decode/size checks, scanner port | Path A | M2/M5 |
| R-11 | P1 | Repository paths drift under two writers | Overlapping diff or duplicate contract | Separate worktrees, ownership checks, Sol merge order | Sol | Every task |
| R-12 | P1 | No authoritative current road-status source exists | Source audit confirms gap | Human-reviewed status workflow, explicit unknown, replay-labelled demo | Sol | M0/M6 |
| R-13 | P2 | Guwahati–Silchar or NH-6 alternative fails feasibility audit | Graph/vehicle/source gate fails | Replace corridor via ADR without changing domain contracts | Sol | M0 |
| R-14 | P2 | Required historical labels are insufficient | Fewer than useful independent event groups | Retain hazard-rule baseline; make verification speed primary outcome | Sol / Path B | M4 entry |
| R-15 | P2 | Source terms prohibit automated retrieval/storage | Terms review fails | Manual permitted snapshots, alternative source, or omit adapter | Sol / Path A | M0/M3 |
| R-16 | P2 | Python/geospatial lock is fragile | Clean installation fails | Exclude unused raster stack; evidence-backed runtime fallback | Path A | M0 |
| R-17 | P2 | GPS consent, retention, and encryption remain undefined | No approved policy before real trace | Use labelled replay only; block real GPS ingestion | Sol | M2/M6 |
| R-18 | P2 | Assamese template lacks qualified review | No reviewer approval | Keep template as draft and block operational release | Sol / Path B | M2/M6 |
| R-19 | P2 | PostGIS transaction and external calls couple failures | Router/alert called inside write transaction | Commit status/audit first; dispatch external action afterward | Both | M1–M3 |
| R-20 | P2 | Backend claims full offline or accessibility completion | Client evidence absent | Trace requirement as backend-supported, client-pending | Sol | M6 |

## 4. Open questions and decision gates

| ID | Question | Required evidence | Decision owner | Latest gate | Default if unresolved |
|---|---|---|---|---|---|
| Q-01 | Does the preserved official SIH text match the dossier’s ten obligations? | Dated official snapshot and requirement diff | Sol / human owner | Before M0 acceptance | Treat dossier reconstruction as provisional and block submission traceability claim |
| Q-02 | Does Guwahati–Silchar provide two vehicle-feasible routes? | Dated graph, GraphHopper result, restriction audit, local review | Sol | M0 corridor gate | Change corridor through ADR |
| Q-03 | Who can authorize each operational status and resolve cross-district conflict? | Named role/jurisdiction matrix from partner or approved demo policy | Human owner / Sol | Before M1 status write | Demo-only seeded authority; no deployment claim |
| Q-04 | Which freshness limit applies to each source and decision type? | Source cadence plus operational-owner review | Sol / domain reviewer | Before M3 live adapter | Mark source unavailable or stale; abstain |
| Q-05 | Which identity provider and claims are available? | Issuer metadata, claims sample, scope mapping | Deployment owner | Before external auth | Test issuer only; no production identity claim |
| Q-06 | What are GPS purpose, precision, retention, and deletion rules? | Approved consent/privacy policy | Human owner / deployment authority | Before real GPS | Labelled synthetic or replay data only |
| Q-07 | Are English and Assamese the correct first operational languages? | Corridor user and native-language review | Human owner | Before M2 template approval | English plus draft Assamese labelled unreviewed |
| Q-08 | Which external notification channel is approved? | Credentials, terms, recipient policy, failure behavior | Human owner | Before M6 | In-app persisted alert only |
| Q-09 | Can source snapshots and derived fixtures be stored and redistributed? | Licence/terms record per source | Sol / data owner | Before fixture commit | Store metadata/hash only or use synthetic fixture |
| Q-10 | Is a supervised model justified? | Frozen labels, independent positives, holdout, owner thresholds | Sol / Terra | M4 entry | Retain transparent baseline |
| Q-11 | What cloud and India-residency boundary applies? | Hosting authority, region, identity, secrets, backup, incident owner | Human owner | Before deployment milestone | Local/replay prototype only |
| Q-12 | Where will the PWA live and who owns its contract tests? | Client repository decision and client owner | Human owner / Sol | Before client integration | Backend publishes OpenAPI/fixtures only |

## 5. Decision-change template

```markdown
### D-XXX: Short decision title

- Context:
- New evidence:
- Previous decision:
- Revised decision:
- Alternatives:
- Reason:
- Consequences:
- Affected paths:
- Affected contracts:
- Required migration or compatibility action:
- Required regression evidence:
```
