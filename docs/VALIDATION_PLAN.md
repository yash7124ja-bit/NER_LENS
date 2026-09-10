# NER LENS validation and Terra review plan

**Authority:** Milestone completion requires executable evidence, not implementation presence.  
**Blocking policy:** Open P0 or P1 findings block integration and milestone completion.

## 1. Validation principles

1. Test the product invariants before broad feature coverage.
2. Prefer deterministic replay fixtures over unreliable live services in CI.
3. Keep one approved live-source smoke test outside the default test suite when terms permit.
4. Validate event time separately from retrieval and server time.
5. Test authorization with forbidden cross-scope access, not only successful access.
6. Test degraded states as first-class behavior.
7. Compare every learned model with declared baselines.
8. Treat an unmeasured claim as unmeasured.
9. Run full gates from a clean checkout after integration.
10. Preserve test output, fixture manifests, model cards, and migration versions in the release evidence bundle.

## 2. Test layers

| Layer | Purpose | Minimum evidence |
|---|---|---|
| Static | Formatting, imports, types, dependency policy | Formatter check, Ruff, mypy, import-boundary test |
| Unit | Domain policies and edge cases | Focused tests for state, freshness, scope, idempotency, ranking, alerts |
| Property | Invariants across generated cases | Idempotent replay, order independence, monotonic penalties |
| Database | Constraints and transaction behavior | Disposable PostGIS, migration up/down, uniqueness and exclusion tests |
| Contract | Path interaction and external envelopes | Frozen JSON fixtures and OpenAPI snapshot |
| Integration | API, database, router fixture, and storage fixture | Transactional end-to-end module cases |
| Replay | Complete mission and failure scenarios | Deterministic source/GPS/report fixtures |
| Security | Auth, upload, SSRF, secret, and scope failures | Negative authorization matrix and malicious fixtures |
| Resilience | External and internal failure behavior | Stale feed, router timeout, model failure, database recovery |
| Performance | Declared prototype hardware and dataset | p50/p95 with data size and concurrency stated |
| Human/field | Workflow effectiveness and safety | Approved protocol, denominators, confidence intervals, stop conditions |

## 3. Product-invariant tests

The following tests are mandatory before the thin slice can be accepted:

- hazard evidence cannot call the status-decision write path;
- a risk result contains no operational-status field;
- an expired `open`, `restricted`, or `closed` decision resolves to `unknown`;
- a model failure returns the approved baseline or `insufficient_evidence`;
- an applicable closure excludes a route for the matching vehicle and direction;
- a non-applicable vehicle restriction does not exclude unrelated profiles;
- no feasible route returns `no_verified_feasible_route` with blocking reasons;
- duplicate mutation with the same idempotency key returns the original result;
- the same idempotency key with a different request hash returns conflict;
- conflicting reports remain independently reviewable;
- partial media upload cannot become complete or reviewed evidence;
- authorization denies another district or mission by default;
- logs contain no access token, media content, or full GPS trace;
- stale or failed feeds cannot become “no hazard”;
- replay and simulation metadata remains visible in API output.

## 4. Milestone gates

### M0: reconnaissance, evidence, and contract freeze

Required checks: preserve a dated official SIH-26002 snapshot and requirement diff, or a signed risk acceptance; audit corridor, two route hypotheses, restrictions, source access/terms/fallbacks, labels, mission, status authority, and `RouteVerificationPolicy`; confirm ownership and contract names; lint links/paths and record the first baseline-commit procedure. Terra P0 blocks pilot/live runtime. The bounded, expiring replay-only exception in `decisions/hackathon-replay-track.md` authorizes only its named tasks and does not count as a P0 pass.

### M1: foundation, identity, corridor, mission schema, and router adapter

Required checks: clean lock installation; API/PostGIS health; migration up/down; auth/object-scope matrix; stable typed segment import; A-owned Path B persistence schema; route-adapter restriction/outage/policy fixtures; canonical error/OpenAPI contracts. Terra focuses on secrets, migration drift, cross-scope access, geometry, and unauthorized persistence coupling.

### M2: evidence, status, risk baseline, and thin slice

Required checks: append-only snapshot/evidence provenance; reviewer-versus-status-authority separation; conflict/expiry/audit transaction; applicable closure exclusion; baseline/abstention behavior; all four route-policy outcomes; end-to-end reviewed status → route change → audit with no model-to-status path.

### M3: offline reports/media, GPS, and alerts

Required checks: idempotent sync without loss or duplicate canonical records; request-hash conflict; quarantine/scan state; malicious media rejection; consented GPS replay/anomaly handling; scoped mission access; post-commit alert creation, dedupe/escalation, reviewed templates, and cursor retrieval.

### M4: ingestion, feature snapshots, and baseline evaluation

Required checks: raw hash/parser provenance; schema/units/time/geometry quarantine; stale-source semantics; point-in-time feature cutoff; immutable dataset manifest; prevalence and hazard-rule baselines; blocked/event-grouped evaluation with declared metrics and uncertainty. Insufficient labels close M4 as `baseline retained`, not fabricated model success.

### M5: conditional ML and operational integration

Entry requires frozen labels, enough independent positive event groups, a held-out complete monsoon, owner-approved thresholds, and Sol approval. When entered, preprocessing/calibration fit only training data; candidate results are baseline-relative and sliced; artifact/checksum/OOD/freshness failures fall back or abstain; routing, mission and alert replay preserves hard constraints and policy outcomes. Any failed entry condition retains the baseline.

### M6: hardening, field, and release evidence

Required evidence:

- corridor and source audit outcome;
- official requirement traceability with working, replayed, simulated, or partner-dependent status;
- corridor/graph manifest and licences;
- migrations and rollback notes;
- model card or explicit baseline-retained report;
- security scan and authorization matrix;
- controlled 100-report sync evidence from the client/backend integration when a client exists;
- accessibility evidence from the client when a client exists;
- backup/restore evidence;
- known limitations and unmeasured outcomes;
- human-reviewed operational language templates;
- field approval/consent records for any real GPS or report data.
- a named client repository and owner before claiming the full SIH system; otherwise the release is explicitly backend-only.

Terra focus: fabricated “live” claims, missing denominators, unapproved data, unsupported NER-wide generalization, and release evidence that cannot be reproduced.

## 5. Terra review protocol

Terra receives:

- milestone/task IDs;
- base and head commits;
- approved contracts;
- ownership matrix;
- executed commands and raw outcomes;
- migrations, fixtures, and provenance manifests;
- known limitations and prior findings.

Terra must inspect the diff and run relevant commands. A summary without adversarial checks is not a review.

Each finding contains:

```text
ID: T-<milestone>-<number>
Severity: P0 | P1 | P2 | P3
Area: architecture | correctness | security | reliability | data | AI/ML | testing | performance | operability
Evidence: file, line, command, response, or reproducible case
Impact: concrete failure or risk
Required correction: observable outcome, not a preferred style
Owner: Path A | Path B | Sol
Blocking: yes | no
Regression evidence required: exact test or command
```

Terra must challenge:

### Architecture

- package imports match ownership and dependency direction;
- no duplicate domain type or alternate contract exists;
- ports exist only at real volatile boundaries;
- no premature service, queue, cache, or framework appeared.

### Correctness

- requirements map to observable behavior;
- state transitions, validity, scope, and conflicts are correct;
- error paths do not invent success or discard evidence.

### Security

- authentication validates issuer, audience, signature, expiry, and required claims;
- authorization checks role plus district/mission scope;
- uploads, egress, secrets, logs, and sensitive outputs are bounded;
- rate and size limits exist at trust boundaries.

### Reliability

- timeouts, retries, idempotency, partial failure, and recovery are explicit;
- external calls do not occur inside database transactions;
- retries cannot duplicate canonical state or alerts.

### Data

- constraints enforce invariants;
- migrations are reversible before release and forward-corrected after sharing;
- timestamps, geometry, scope, and relationships are normalized;
- no future information enters historical features.

### AI/ML

- target and observation process are distinguished;
- baselines precede candidates;
- evaluation is grouped in time and by event;
- explanations describe model associations, not physical causation;
- abstention and rollback are executable.

### Testing and performance

- negative cases and integration boundaries have evidence;
- passing unit tests do not substitute for database/router/replay tests;
- performance claims state hardware, data volume, concurrency, and percentiles.

### Operability

- health endpoints distinguish process, dependency, and source health;
- logs identify request/source/mission/model without exposing sensitive payloads;
- deployment, backup, restore, and failure diagnostics are executable.

## 6. Finding resolution

- Path owners fix findings in their owned modules.
- Sol fixes or coordinates shared-contract and integration findings.
- Every P0/P1 correction includes a regression test or reproducible command.
- Terra rechecks the correction; the implementing agent cannot self-close it.
- Sol records accepted P2 debt with owner and latest permitted milestone.
- P3 findings do not expand scope unless Sol approves them.

## 7. Release stop conditions

Stop release or field activity if:

- an applicable active closure can appear in a recommended route;
- a hazard or model can mutate operational status;
- provenance cannot be reconstructed;
- accepted evidence is lost or duplicated;
- GPS, identity, or mission data crosses authorization scope;
- risk is consistently read as confirmed closure;
- source terms prohibit implemented collection or storage;
- field validation would place participants at risk;
- replay, simulated, or paper results are presented as live system results.
