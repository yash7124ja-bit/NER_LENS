# NER LENS Parallel Execution Plan

> **For agentic workers:** This is the coordination contract for `docs/MILESTONES.md`. Execute only owned tasks, keep changes reviewable, and use the forced-single-working-tree procedure when worktrees are unavailable.

**Goal:** Let Path A, Path B, and Sol progress independently against explicit contracts while preserving migration ownership, safety gates, reversible integration, and a truthful release.

**Architecture:** Path A owns the foundation and operational truth; Path B owns mission/routing/risk/alerts; Sol owns shared contracts, application wiring, dependency locks after baseline, cross-module tests, and the OpenAPI snapshot. Domain services communicate through contracts and service calls, not direct writes to another module's tables.

**Tech Stack:** Python/FastAPI/PostGIS/Alembic; GraphHopper; pytest/Ruff/mypy; Docker Compose for the backend prototype.

**Spec:** `docs/MILESTONES.md`; source: the two SIH26002 primary design documents at the workspace root.

## 1. Ownership and file boundaries

| Area | Path A | Path B | Sol/shared rule |
|---|---|---|---|
| Package/tool baseline | Initial `A-M1-01` files | Forbidden | Sol approves versions and owns later lock changes |
| Configuration and DB session | Owns implementation | Consumes | Contract changes require Sol approval |
| Identity and authorization | Owns | Consumes | Sol owns auth/error contract |
| Corridor and typed segments | Owns | Consumes | Sol approves public DTO changes |
| Evidence, review, status, audit | Owns | Read-service consumer only | Status safety invariant is frozen |
| Ingestion and source health | Owns | Consumes | Sol approves source modes and public health DTO |
| Migrations/model registry | Exclusive owner | Schema request only | Sol approves schema contract; never authors migration |
| Missions and GPS | Schema request/authorization support | Owns | Sol owns public API composition |
| Routing and GraphHopper | Provides resolved segment state | Owns | Sol owns route response contract |
| Risk/model | Provides features/manifests | Owns | Sol owns promotion contract and gate decision |
| Alerts/templates | Provides material status events | Owns | Sol approves contract; language reviewer approves copy |
| Domain tests | Own Path A suites | Own Path B suites | Each path forbidden from weakening the other suite |
| Contract/integration tests | Supplies fixtures | Supplies fixtures | Sol exclusively owns canonical cross-path tests |
| `src/ner_lens/app.py` | Forbidden after initial handoff | Forbidden | Sol exclusive owner |
| `src/ner_lens/contracts/**` | Consumes | Consumes | Sol exclusive owner |
| `compose.yaml` and release wiring | Consumes | Consumes | Sol exclusive owner |
| Documentation | Own module evidence | Own module evidence | Sol owns these seven control documents and release truth |

“Consumes” never authorizes direct writes to another module's tables or files. Integration occurs through the contracts in [CONTRACTS.md](./CONTRACTS.md).

### Path A — foundation and operational truth

Owns identity, district scope, corridor versions/segments, evidence/provenance, review/status, source snapshots/adapters, feature/label manifests, sync protocol, all Alembic migrations, and Path A tests.

Allowed roots:

- `src/ner_lens/identity/**`, `src/ner_lens/security/**`, `src/ner_lens/corridor/**`, `src/ner_lens/evidence/**`, `src/ner_lens/status/**`, `src/ner_lens/audit/**`, `src/ner_lens/media/**`, `src/ner_lens/persistence/**`, `src/ner_lens/ingestion/**`, `src/ner_lens/features/**`, `src/ner_lens/sync/**`
- `src/ner_lens/config.py`, `src/ner_lens/db.py`, `src/ner_lens/common/idempotency.py`, `src/ner_lens/common/time.py`
- `migrations/**`, `ops/scripts/**` and `ops/backups/**` owned by A
- `pyproject.toml` and `uv.lock` or equivalent only for the initial `A-M1-01` baseline; Sol owns later dependency/lock changes
- `data/manifests/**`, A-owned `data/corridor/**`
- `tests/path_a/**`

Forbidden without an approved contract change:

- `src/ner_lens/missions/**`, `src/ner_lens/gps/**`, `src/ner_lens/routing/**`, `src/ner_lens/risk/**`, `src/ner_lens/alerts/**`
- `src/ner_lens/contracts/**`, lockfiles, and any frontend repository

### Path B — mission and decision intelligence

Owns missions/GPS, GraphHopper routing, hard constraints, route scoring, baseline/candidate risk, ETA, alert rules/templates, and Path B tests.

Allowed roots:

- `src/ner_lens/missions/**`, `src/ner_lens/gps/**`, `src/ner_lens/routing/**`, `src/ner_lens/risk/**`, `src/ner_lens/alerts/**`
- `data/templates/**`, B-owned `data/corridor/graphhopper/**`, `models/cards/**`, `models/artifacts/**`
- `tests/path_b/**`, B-owned `tests/replay/**`

Forbidden:

- `migrations/**` (submit a schema request to A)
- `src/ner_lens/identity/**`, `src/ner_lens/persistence/**`, status approval, source adapter internals, lockfiles, public precise GPS, automatic closure logic

### Sol — shared contracts, wiring, and gates

Owns canonical Pydantic/OpenAPI contracts, API composition, shared wiring, dependency and lock changes only after baseline, cross-module tests, OpenAPI snapshots, release assembly, and coordination metadata.

Allowed roots:

- `src/ner_lens/contracts/**`, `src/ner_lens/app.py`, `src/ner_lens/api/**`
- `compose.yaml` and shared deployment wiring
- `tests/contracts/**`, `tests/integration/**`, `tests/e2e/**`
- `docs/openapi/**`, `docs/release/**`, coordination docs
- `pyproject.toml`, `uv.lock` or equivalent only after baseline and dependency review

Forbidden:

- domain migrations; direct table writes; silent field renames; changing evidence precedence/status transitions/model thresholds; adding speculative dependencies.

## 2. Branch and worktree strategy

Preferred layout when Git worktrees are available:

```text
main                protected integration branch and tagged last-green baseline
path-a              foundation, identity, corridor, evidence, ingestion, migrations, A tests
path-b              missions/GPS, GraphHopper, risk, alerts, B tests
sol                 contracts, wiring, locks after baseline, cross-module tests, OpenAPI
```

This layout is permitted only after the human accepts the seven specifications and Sol/human creates the first shared baseline commit. The current unborn/uncommitted tree is documentation work, not a branchable integration baseline.

- Create M0 worktrees from the accepted specification baseline commit. Synchronize all paths to the accepted M0 contract/P0 commit before M1 runtime work.
- Use short task branches inside each worktree: `path-a/A-M2-02-status`, `path-b/B-M4-01-baseline`, `sol/S-M5-01-locks`.
- One task branch changes one ownership boundary and ends with its own tests.
- Never use `git reset --hard`, `git checkout --`, or broad cleanup to resolve overlap. Preserve another agent's changes and resolve through a contract or merge commit.
- Keep generated OpenAPI, model cards, manifests, and lockfiles reviewable; do not mix them with unrelated refactors.
- Every merge to `main` is a checkpoint with a named test command and rollback tag.

### Forced-single-working-tree procedure

Use this when worktrees are unavailable, the repository is empty/uninitialized, or a platform only exposes one checkout:

1. Sol records the current commit/tree state in `docs/release/working-tree-lock.md` and creates the baseline directories.
2. A, B, and Sol work serially in the order `A → B → Sol`; only one task is active at a time.
3. Before editing, the active owner records task ID, allowed paths, base commit, and expected files in the lock file. The active owner must not touch another path owner’s files.
4. After the task test passes, the owner creates a small commit or patch checkpoint. If Git is not initialized, preserve a dated patch/diff in `docs/release/checkpoints/` and do not overwrite files outside the task allowlist.
5. The next owner runs the baseline checks and reads the prior task’s outputs before editing. No parallel terminal/session edits are permitted.
6. Sol performs integration and generates the OpenAPI snapshot only after A/B checkpoints are present.
7. If a conflict appears, stop the active task, record a schema request, and ask the owner of the conflicting path to resolve it. Do not edit through the conflict.

This procedure is slower but prevents a shared empty repository from producing unreviewable interleaved changes.

## 3. Synchronization cadence and gates

### Contract freeze points

- **CF-0 (M0):** names, ownership, safety boundary, corridor ID, graph version, source terms, status/risk split, and initial endpoint envelopes.
- **CF-1 (M1):** `AuthContext`, `CorridorVersion`, `RoadSegment`, migration transaction boundary, error envelope, mission/route contracts.
- **CF-2 (M2):** `SourceSnapshot`, `EvidenceRef`, `OperationalStatus`, `ReviewAction`, `RiskOutlook`, `RouteComparison`; thin slice must pass.
- **CF-3 (M3):** sync/media/GPS/alert state machines and offline error semantics.
- **CF-4 (M4):** dataset manifest, model card, source-health and degraded-mode contracts.
- **CF-5 (M6):** release OpenAPI snapshot; no contract changes after this without a release exception and a new version.

At each freeze point:

1. Sol publishes the contract diff and generated schema if runtime routes exist.
2. A verifies migration impact and creates any needed revision.
3. B runs route/risk/mission/alert fixture tests against the contract.
4. All owners acknowledge compatibility or submit a schema request.

### Terra gates

- **Terra P0:** before M1 implementation. Requires corridor audit, two route hypotheses, restriction review, source terms/fallbacks, named status authority and evidence reviewer, label feasibility, and an essential-medicine mission. Failure means stop/change corridor.
- **Terra P1:** before release or candidate model promotion. Requires zero applicable closure/vehicle violations in replay, reconstructible provenance, honest stale/failed behavior, auth matrix, zero offline loss/duplicate canonical records, reviewed templates, restore test, and blocked baseline-relative model evaluation. Failure means release block and rollback to the last green baseline.

## 4. Schema request protocol

Only A edits migrations. Any owner may request a schema change with a small record in `docs/schema-requests/` (Sol may create the directory; A owns the resulting migration).

Required fields:

```yaml
request_id: SR-YYYYMMDD-NN
requester: path-a|path-b|sol
task_id: A-Mx-yy or B-Mx-yy or S-Mx-yy
reason: one operational sentence
entity: table-or-contract-name
change: add|alter|index|constraint|remove
fields_or_rule: exact names, types, nullability, enum, index, or constraint
backward_compatibility: additive|dual-read|breaking
data_migration: exact backfill/default/none
rollback: reversible migration or roll-forward correction
consumers: named interfaces/tests
acceptance_test: one runnable test name
owner_ack: required owner names
```

Rules:

- Additive changes are preferred: nullable field/table, dual-read, then required after consumers migrate.
- Breaking changes require a versioned contract, compatibility window, OpenAPI update, and explicit Terra review if operational data is affected.
- A migration must not delete evidence, audit events, GPS originals, or source snapshots. Correct with supersession/expiry/roll-forward.
- The requester must include a fixture and a rollback test. “Needed by service” without exact fields is rejected.
- A returns migration name, checksum, up/down result, and affected interface. Sol updates the canonical contract only after A's revision is green.

## 5. Integration and merge order

1. **M0 artifacts:** after the accepted specification baseline commit, A produces the corridor/source ledger, B the route audit, and Sol the official snapshot/diff plus contract/policy freeze. Terra P0 decision is merged first.
2. **Foundation:** A-M1-01 migrations/foundation, A-M1-02 identity, A-M1-03 corridor and A-M1-04 Path B persistence schema. Sol-M1 shared package follows the same baseline; B waits for its persistence contract, corridor and transaction boundary.
3. **B domains:** B-M1-01 mission/GPS and B-M1-02 GraphHopper adapter run against the frozen M1 contracts. B does not add migrations.
4. **Operational truth:** A-M2-01 evidence then A-M2-02 status/review. B-M2-01 baseline reads these services; Sol-M2 wires the thin slice.
5. **Thin-slice checkpoint:** merge S-M2-01 only after an end-to-end replay shows reviewed status → route change → audit. This is the first integration baseline.
6. **Offline/mission/alerts:** A-M3-01 → A-M3-02, B-M3-01/B-M3-02, then S-M3-01. A migrations and media security boundary land before B/S consumers that require them.
7. **Ingestion/risk:** A-M4-01 → A-M4-02, B-M4-01, S-M4-01. Baseline results are frozen before any candidate model or dependency expansion.
8. **Conditional ML and route quality:** B-M5-01 → B-M5-02 → B-M5-03. Candidate mode is feature-flagged/metadata-selected and can fall back to baseline.
9. **Dependency/lock changes:** S-M5-01 only after the baseline is green and each package request is approved. Lockfile changes are a separate reviewable merge.
10. **Release:** A-M6-01 and B-M6-01 in parallel where paths are independent; S-M6-01 runs last. Terra P1 must pass before the release tag.

If a task needs a later task, it may consume only the published interface/fixture, not the unfinished implementation. If a contract is not frozen, the task pauses and submits a schema request rather than guessing.

## 6. Dependency and lockfile policy

- Baseline means the repository can run the foundation health check, contract tests, and migration test without adding nonessential packages.
- Before baseline, Sol may declare versions from the primary stack but does not modify lockfiles to solve speculative future work.
- After baseline, a dependency request must state capability, why stdlib/native/already-installed options are insufficient, license, version pin, security impact, bundle/runtime cost, and rollback.
- Sol owns `uv.lock` or equivalent; A/B provide requested package names and exact use sites, not direct edits.
- Reject packages that duplicate existing HTTP, validation, storage, routing, retry, or localization capabilities. No dependency is added for a single trivial helper.
- Every lockfile change runs clean install, lint/type/build, relevant unit tests, cross-module tests, and dependency/security scan.

## 7. Validation matrix

| Gate | Minimum evidence | Owner | Blocks |
|---|---|---|---|
| M0/P0 | corridor/source/label/reviewer/mission ledger; route audit | A/B/Sol | all implementation |
| M1 | migration up/down; auth matrix; segment import; contract tests | A/Sol | B domain merge |
| M2 thin slice | reviewed status changes route; audit trail; OpenAPI checkpoint | A/B/Sol | M3 |
| M3 offline | zero accepted-record loss; zero duplicate canonical records; conflict/media fixtures | A/B/Sol | M4 release claims |
| M4 baseline | immutable dataset manifest; leakage report; baseline card; source health | A/B/Sol | candidate ML |
| M5 candidate | blocked temporal/event-group evaluation; promotion decision; route metrics | B/Terra | candidate mode |
| M6/P1 | security, restore, accessibility, resilience, performance, replay evidence | A/B/Sol/Terra | release tag |

The smallest complete automated gate is:

```text
format/lint
→ type checks
→ unit/property tests
→ migration up/down on disposable PostGIS
→ source contract fixtures
→ leakage/evaluation checks
→ API + PostGIS + GraphHopper integration
→ authorization matrix
→ offline-sync backend protocol
→ health/resilience/replay smoke
→ OpenAPI snapshot comparison
```

## 8. Rollback and failure handling

### Code and contracts

- Every merge to `main` receives a checkpoint tag or patch artifact and a test transcript.
- A failed integration rolls back to the previous passing tag; do not revert unrelated user work or reset the whole tree.
- Contract changes use additive/dual-read migration first. Breaking changes require a versioned endpoint/contract and a compatibility window.
- OpenAPI snapshots are regenerated from runtime code; if the snapshot changes unexpectedly, stop the merge and investigate.

### Database and migrations

- Test every revision up/down on a disposable PostGIS database before merge.
- Production rollback is normally roll-forward: restore backup or apply a corrective migration. Do not downgrade a production database when it can destroy evidence or audit history.
- Preserve source snapshots, evidence, status decisions, GPS originals, media hashes, and audit events. Expire/supersede rather than delete.
- A restore test must prove that a status decision, route decision, alert, and provenance chain survive recovery.

### Model, route, and source behavior

- Candidate ML is selectable by model metadata and must fall back to the transparent baseline on artifact/checksum/schema/OOD/freshness failure.
- GraphHopper outage returns a labelled degraded/no-feasible result; it does not invent a route or convert risk into closure.
- Source failure becomes `stale|failed|quarantined`; never “no hazard” or a permanent green/open state.
- A release with Terra P1 failure remains on the last passing baseline and labels any replay/simulation explicitly.

## 9. Safe handoff packet

Every completed task hands the next owner:

- task ID and commit/patch checkpoint;
- files changed and files intentionally untouched;
- contract/interface version and schema requests;
- commands run and result;
- fixtures/manifests/checksums produced;
- known limitations and whether they block Terra P0/P1;
- exact next dependency and rollback pointer.

No task is complete on “code exists.” It is complete only when its acceptance tests, integration validation, and handoff packet are present as specified in `docs/MILESTONES.md`.

## 10. Unresolved decisions requiring explicit owner choice

- Which approved external identity provider will be used beyond the test issuer; the contract remains OIDC-shaped until chosen.
- Which source adapters are lawful and technically reachable at implementation time; replay fixtures remain the fallback.
- Whether a field partner can provide enough independently verified event groups for candidate ML; otherwise ship the baseline and verification workflow.
- Which operational owner ratifies alert thresholds, route weights, retention, and model promotion criteria; engineering defaults are not authority decisions.
- Whether the two-day corridor audit passes; if not, record the rejected corridor and select another before M1.


