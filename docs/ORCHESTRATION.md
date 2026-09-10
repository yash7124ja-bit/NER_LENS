# NER LENS engineering orchestration

**Status:** Approved first-run engineering control specification  
**Repository:** `D:/SIH-2026/NER_LENS`  
**Scope:** Backend repository only  
**Primary prototype:** Essential-medicine movement on a provisional Guwahati–Silchar corridor  
**Control owner:** GPT-5.6 Sol, principal engineering orchestrator

## 1. Purpose

This document controls how two independent implementation paths contribute to one backend without changing architecture, contracts, or shared files independently. It is the entry point for Sol, Path A, Path B, and Terra.

No implementation agent may start from the research documents alone. Every implementation task must reference an approved task in [MILESTONES.md](./MILESTONES.md), the applicable contract in [CONTRACTS.md](./CONTRACTS.md), and its ownership boundary in [PARALLEL_EXECUTION_PLAN.md](./PARALLEL_EXECUTION_PLAN.md).

## 2. Reconnaissance record

On 10 September 2026 the repository contained only `.git/` internals:

- branch `main` existed with no commits;
- no source, configuration, schema, migration, test, CI, documentation, or infrastructure files existed;
- no repository convention could override the project documents;
- no test or integration could be claimed as working.

The two inspected primary project documents were:

1. `D:/SIH-2026/SIH-26002-AI-Based-Smart-Logistics-and-Accessibility-Intelligence-Platform-for-North-Eastern-Region-NER.md`
2. `D:/SIH-2026/SIH-26002-TECH-STACK-IMPLEMENTATION-AND-VALIDATION.md`

The researched dossier reconstructs the SIH requirements from a dynamic official page. It is not a preserved copy of the official statement. Requirement verification against a dated local snapshot remains a pre-implementation evidence task.

## 3. Authority hierarchy

Use this order when sources disagree:

1. Preserved official SIH-26002 statement with retrieval date and requirement IDs.
2. Explicit acceptance criteria approved by Sol and the human project owner.
3. Technical implementation and validation blueprint.
4. Approved repository contracts and accepted architecture decisions.
5. Existing implemented behavior and tests.
6. Engineering practice.
7. Agent assumptions.

An agent must not silently resolve a conflict. It must create a decision request containing the conflicting sources, affected task IDs, recommended interpretation, migration or compatibility impact, and proposed test change.

## 4. Product invariants

These rules outrank implementation convenience:

1. Hazard data and model output cannot create, renew, or remove an operational road status.
2. Only an authorized status decision can assert `open`, `restricted`, or `closed`.
3. Expired evidence transitions to `unknown` unless a valid decision renews it. The system never assumes reopening.
4. Every decision-relevant record preserves provenance, event time, system receipt time, validity, source health, and version.
5. Missing evidence is not negative evidence.
6. Replayed, simulated, synthetic, and partner-dependent behavior is labelled.
7. Routing enforces vehicle, direction, structure, and active status constraints before risk scoring.
8. No feasible verified route is a valid result.
9. Every mutation is idempotent within a documented scope.
10. Authorization is enforced on the server by role and object scope.
11. The backend must support a complete non-map representation of critical state for a future accessible client.
12. Documentation may describe only behavior that exists or clearly label planned behavior.

## 5. Approved system boundary

This repository owns:

- FastAPI application and versioned HTTP contracts;
- PostgreSQL/PostGIS schema and migrations;
- identity claim verification and server authorization;
- corridor, infrastructure segment, evidence, review, operational status, and audit logic;
- mission, GPS batch, routing, risk, and alert logic;
- source adapters, replay fixtures, immutable snapshot metadata, and scheduled ingestion commands;
- media metadata, quarantine state, storage adapter contract, and idempotent upload protocol;
- model baselines, conditional supervised evaluation, model metadata, and abstention;
- backend tests, Compose runtime, health endpoints, and release evidence.

This repository does not own:

- React/PWA implementation or browser service-worker behavior;
- public turn-by-turn navigation;
- autonomous dispatch or safety certification;
- production identity-provider administration;
- unrestricted government, ULIP, carrier, or private fleet access;
- LLM, RAG, computer-vision, vector-store, blockchain, or multi-agent product features.

The backend provides contracts required by a separate future PWA. Offline client persistence is outside this repository; server idempotency, conflict preservation, media completion, and replay safety are inside it.

## 6. Roles and decision rights

### Sol: orchestration and integration authority

Sol owns:

- architecture and scope decisions;
- requirement traceability;
- shared contracts and their versions;
- task assignment and dependency order;
- shared-file change approval;
- integration commits and merge order;
- interpretation of Terra findings;
- milestone completion decisions.

Sol does not accept work because code exists. Sol accepts only after the milestone commands and evidence defined in [VALIDATION_PLAN.md](./VALIDATION_PLAN.md) pass.

### Path A: GPT-5.6 Luna

Path A owns:

- initial Python package and lock baseline during `A-M1-01` under Sol-approved dependencies;
- configuration and database session;
- all Alembic migrations;
- identity and authorization;
- corridor versions and infrastructure segments;
- source snapshots, evidence, field reports, reviews, status decisions, and audit;
- ingestion adapters and replay normalization;
- idempotency services;
- Path A tests and documentation attached to those modules.

Path A produces trusted operational state. It must not redefine Path B contracts or wire the final application without Sol review.

### Path B: Claude Sonnet 5

Path B is launched by the human project owner in Claude Code. Path B owns:

- missions and GPS batches;
- routing contracts implementation and GraphHopper adapter;
- vehicle feasibility and route ranking;
- transparent risk baseline and conditional model implementation;
- alerts, reviewed template selection, deduplication, and delivery records;
- Path B tests and documentation attached to those modules.

Path B consumes approved operational state. It must never write authoritative status or edit Path A files.

### Terra: adversarial verifier

Terra reviews architecture, correctness, security, reliability, data, AI/ML, testing, performance, and operability. Terra classifies findings:

- `P0`: catastrophic or safety/security blocking defect;
- `P1`: serious correctness, security, data, or architectural defect;
- `P2`: important non-blocking defect with a required owner and due milestone;
- `P3`: improvement suggestion.

Any open P0 or P1 blocks the milestone. Sol may reject a finding only with written evidence and an updated decision record.

## 7. Controlled interfaces

The following are shared and cannot drift silently:

- identifier and time rules;
- public enums and state machines;
- error envelope and request correlation;
- authentication context and authorization semantics;
- OpenAPI paths and DTOs;
- source-adapter envelope;
- resolved segment state;
- risk result and abstention;
- routing request and alternatives;
- mission/GPS batch protocol;
- alert event and template variables;
- idempotency and optimistic-conflict behavior;
- audit-event fields;
- schema invariants and retention metadata.

Path owners may implement behind these contracts. Only Sol may approve a breaking change.

## 8. Contract-change protocol

When a controlled interface must change:

1. The discovering path stops dependent work.
2. It records the old contract, proposed contract, reason, compatibility impact, affected task IDs, affected tests, and data migration need.
3. Sol identifies all consumers and assigns a contract version.
4. Path A authors any required migration after approval.
5. Sol updates [CONTRACTS.md](./CONTRACTS.md) before implementation continues.
6. Both paths rebase or synchronize to the contract commit.
7. Contract tests fail against the old behavior and pass against the approved behavior.
8. Terra checks for silent alternate fields, duplicate enums, and compatibility gaps.

Breaking changes are not accepted through an implementation pull request without the preceding contract decision.

## 9. Milestone lifecycle

Every milestone follows this sequence:

1. Sol confirms prerequisite decisions and freezes contracts for that milestone.
2. Sol issues Path A and Path B task packets with allowed and forbidden files.
3. Each path starts from the same approved integration commit in a separate worktree.
4. Each path writes a failing test before non-trivial behavior.
5. Each task ends with its scoped verification and one task-ID commit.
6. Terra reviews each completed path independently.
7. The responsible path fixes P0/P1 findings and adds regression evidence.
8. Sol integrates Path A first when it changes trusted state or migrations.
9. Path B rebases onto the new integration head and resolves only its owned conflicts.
10. Sol wires shared application files and cross-module tests.
11. The full milestone gate runs from a clean checkout.
12. Sol records completion or keeps the milestone open with named blockers.

## 10. Git and synchronization policy

### Required mode

- `main` remains the protected integration branch.
- Each milestone begins with a Sol-owned contract commit.
- Path A branch: `path-a/<milestone-id>-<short-name>`.
- Path B branch: `path-b/<milestone-id>-<short-name>`.
- Terra review branches contain findings or tests only when Sol explicitly requests them.
- Each active branch uses a separate Git worktree.
- Commits are small and begin with the task ID, for example `M1-A2 feat: enforce status expiry`.

### Merge order

1. Contract and shared baseline.
2. Path A schema and trusted-state implementation.
3. Path B rebase on the accepted Path A integration commit.
4. Path B complementary implementation.
5. Sol-owned application wiring and cross-module tests.
6. Terra re-review of resolved P0/P1 findings.
7. Full clean-checkout regression gate.

### If one working tree is unavoidable

Two agents must not write concurrently. Sol serializes file-changing turns. Parallel work is limited to read-only analysis, review, and test-plan preparation. The next writer starts only after a clean commit and ownership check.

### Conflict rules

- Never resolve a conflict by taking an entire side without reading both changes.
- The owner of a module resolves its implementation conflicts.
- Sol resolves shared-contract, dependency, app-wiring, Compose, and OpenAPI conflicts.
- Path B never edits a Path A migration to resolve a branch conflict.
- Once a migration has been shared, rollback uses a forward corrective migration, not history rewriting.
- Code rollback uses `git revert` of the responsible task or merge commit.

## 11. Clean handoff requirements

Every task handoff contains:

- task ID and commit hash;
- changed files;
- interfaces consumed and produced;
- commands executed with outcomes;
- known limitations;
- migrations and rollback notes;
- new configuration names without secrets;
- fixture provenance and licence note;
- unresolved P2/P3 findings.

Uncommitted changes, failing tests, undocumented contract changes, or unexplained generated files make a handoff invalid.

## 12. Conditions to begin work

M0 evidence/audit work may begin only when all of these are true:

- the seven first-run specification documents exist and agree;
- backend-only repository scope is confirmed;
- Guwahati–Silchar is recorded as provisional pending the corridor gate;
- Path A alone owns migrations and the database model registry;
- Sol alone approves shared contracts and application wiring;
- Path A and Path B have explicit allowed and forbidden file lists;
- the M0 verification command and Terra blocking policy are recorded;
- no P0/P1 finding remains against the first-run specifications;
- the human accepts the final seven specifications and Sol/human creates their first shared baseline commit; an unborn or uncommitted tree cannot seed worktrees;
- the human project owner authorizes M0 evidence/audit work.

Runtime implementation begins only after M0 additionally preserves a dated official SIH-26002 snapshot and requirement diff (or signed risk acceptance), accepts the corridor/source/authority/label/route-policy audits, freezes the M0 contracts, and passes Terra P0. A full-SIH release additionally requires a named client repository and client owner; without them, release claims remain backend-only.

## 13. Exact next actions after authorization

### GPT-5.6 Luna

Execute only `A-M0-01` from [MILESTONES.md](./MILESTONES.md): produce the corridor, source, terms, reviewer, and label-feasibility ledger. After Sol accepts `S-M0-01` and Terra passes P0, Luna may receive `A-M1-01` for the backend package/database foundation. Do not begin domain features or real integrations before those gates.

### Claude Sonnet 5

Read all seven specifications and execute only `B-M0-01` in its own worktree: audit GraphHopper/OSM route feasibility against the provisional corridor. Begin `B-M1-01` or `B-M1-02` only after Sol publishes the accepted M0 contract commit and Terra passes P0. Do not create schemas, migrations, shared enums, or alternative application wiring.

### GPT-5.6 Terra

Review `A-M0-01`, `B-M0-01`, and `S-M0-01` against the P0 evidence gate. Attempt to disprove corridor feasibility, source/terms validity, authority ownership, label feasibility, route restrictions, and contract consistency before any application implementation begins.
