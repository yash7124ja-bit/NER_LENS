# B-M0-01 — Route and GraphHopper feasibility audit

**Status:** Path B draft audit, provisional. Not a Terra P0 sign-off; not an
Alright-to-implement signal for B-M1-02.
**Owner:** Path B (Claude Sonnet 5)
**Branch / commit:** `path-b/m0-route-audit`, baseline `f6cfd51`
**Task:** `B-M0-01` per `docs/MILESTONES.md`
**Depends on (per MILESTONES.md):** `A-M0-01` draft corridor bounds and candidate endpoints.

## 0. Reconciliation status with A-M0-01 (read first)

As of this audit, `docs/decisions/corridor-audit.md` (A-M0-01's output) **does
not exist**. This was verified directly by inspecting the `path-a` worktree
(`D:/SIH-2026/NER_LENS/.worktrees/path-a`, branch `path-a/m0-audit`, at the
same baseline commit `f6cfd51`): no `docs/decisions/` or `data/` directory
exists there yet.

Per the explicit Path B task packet for this session, this audit proceeds
using the **provisional** Guwahati–Silchar corridor and NH-6 alternative
exactly as described in the two primary SIH-26002 source documents, marked
provisional throughout. **This does not satisfy full B-M0-01 reconciliation.**
Before this audit can be treated as complete against `docs/MILESTONES.md`,
Path B (or Sol) must diff this document and `data/corridor/route-manifest.yaml`
against A-M0-01's published `corridor_id`, six named audit bands, route
buffer, and administrative-unit list, and update any field that disagrees.
That reconciliation step is recorded as an **open item**, not fabricated as
done. See section 7 (Known limitations) and the handoff at the end of this
document.

## 1. What this audit is, and what it is not

This is a **desk audit** of route feasibility and OSM-representable
restriction coverage for the provisional corridor, built from:

- named authority documents already cited in the source dossiers (NHAI
  section annexure, NHIDCL Assam corridors, the Parliamentary highway
  record, the PIB Mawlyngkhung–Panchgram approval), and
- peer-reviewed landslide-susceptibility literature for NH-27/NH-627 and
  Dima Hasao already cited in `SIH-26002-TECH-STACK-IMPLEMENTATION-AND-VALIDATION.md`.

It is **not**:

- a processed real Geofabrik OSM PBF extract,
- a live or replayed GraphHopper routing result,
- a claim that any specific OSM way, node, or tag exists as described,
- a claim about current, real-world road passability or legality.

No self-hosted GraphHopper instance was deployed and no OSM extract was
downloaded or parsed in this environment for this task. Building and
processing the real North-Eastern Zone extract, running GraphHopper against
it, and importing stable segment IDs is explicitly **A-M1-03 / B-M1-02**
scope, gated on Terra P0 and the accepted M0 contract commit, per
`docs/ORCHESTRATION.md` section 13 ("Do not begin B-M1-01 or B-M1-02...").

To exercise the routing hard-constraint policy deterministically without a
real extract, this audit constructs a small, explicitly labelled **synthetic
replay fixture graph** (`data/corridor/graphhopper/fixture_graph.v1.json`,
`"label": "synthetic_replay_fixture"`, `"is_real_osm_extract": false`). Every
band in that fixture records its citation basis and an honest
`missing_legality_data` list. This follows `ARCHITECTURE.md` D-008
(replay-first integrations) and the project rule that "any replay,
simulator, or synthetic record is visibly labelled and cannot be presented
as live coverage."

## 2. Candidate routes audited

See `data/corridor/route-manifest.yaml` for the machine-readable form.

| Route ID | Description | Role | Basis |
|---|---|---|---|
| `route_nh27_primary` | Guwahati (Jalukbari) → Nagaon → Doboka → Lanka/Lumding → Maibang → Harangajao/Balachera hill section → Silchar, via NH-27 | Primary | NHAI annexure, NHIDCL Assam corridors, Parliamentary highway record |
| `route_nh6_alternative` | Guwahati → Shillong → Jowai → Panchgram/Silchar, via NH-6 | Alternative | Source dossier; PIB Mawlyngkhung–Panchgram approval (planned-corridor context only) |

Route buffer: 5 km around both candidates. Hazard-context buffer: 20 km.
Administrative units: Kamrup Metropolitan, Nagaon, Hojai, Dima Hasao, Cachar.
These numbers are copied from the source documents' stated defaults
(`SIH-26002-TECH-STACK-IMPLEMENTATION-AND-VALIDATION.md` section 7, "Exact
extraction boundary") and are themselves subject to A-M0-01/Sol confirmation.

**`route_nh6_alternative` is explicitly not asserted as currently open.** The
Mawlyngkhung–Panchgram high-speed corridor referenced by PIB is a project
approval, not evidence of present usability. It is represented in the
fixture with `hgv: "no"` and an explicit `planned_infrastructure_warning`
field precisely so it cannot be silently treated as an open road (per
ARCHITECTURE.md section 2, "Never place planned infrastructure into the
live routing graph as open road").

## 3. Vehicle profile / restriction-coverage matrix

Three vehicle profiles per `docs/MILESTONES.md` non-negotiable project
rules: `light_goods`, `rigid_truck`, `emergency`. Full definitions in
`data/corridor/graphhopper/vehicle_profiles.yaml`.

| Profile | max_weight_t | max_height_m | hgv_exempt | Notes |
|---|---:|---:|---|---|
| `light_goods` | 3.5 | 2.5 | yes | Least restricted |
| `rigid_truck` | 16.0 | 3.8 | no | Primary essential-medicine mission candidate profile |
| `emergency` | 7.5 | 3.0 | yes (traffic-control only) | Physical clearance/weight limits still apply — see ARCHITECTURE.md edge case "Emergency vehicle has legal exemption" |

Restriction-category coverage recorded per band (topology, surface,
bridge/tunnel, access, `maxheight`, `maxweight`, `hgv`, construction, turn,
direction) — see `fixture_graph.v1.json`. Coverage summary:

| Category | Recorded for every band? | Honest gap |
|---|---|---|
| Topology (routable) | Yes | Desk-audit assertion, not GraphHopper-verified |
| Surface | Yes (`paved`/`unverified`) | NH-6 alternative surface is `unverified` for 2 of 3 bands |
| Bridge/tunnel | Yes (`segment_type`) | Only 1 bridge modelled; real corridor almost certainly has more river crossings not yet inventoried |
| Access | Yes (free-text note) | Not a substitute for a real OSM `access` tag audit |
| `maxheight_m` | Recorded, often `null` | 8 of 10 bands have unknown `maxheight_m` — disclosed in `missing_legality_data` |
| `maxweight_t` | Recorded, often `null` | 8 of 10 bands have unknown `maxweight_t` — disclosed |
| `hgv` | Recorded, often `unknown` | 4 of 10 bands have unknown `hgv` — disclosed |
| Construction | Yes (boolean) | Only reflects the single documented Mawlyngkhung–Panchgram caveat; not a live construction-tag scan |
| Turn restrictions | Recorded (empty list everywhere) | No turn-restriction data has been audited; empty means "not yet audited," not "confirmed none exist" |
| Direction | Yes | Only 1 band modelled as directionally restricted |

This table is the audit's answer to "missing legality data must be visible":
**most heavy-vehicle structural limits along this corridor are unknown, not
zero.** `tests/replay/routing/test_route_replay_fixtures.py::test_missing_legality_data_is_visible_not_silently_assumed`
enforces that every unknown value is disclosed rather than silently treated
as permissive.

## 4. Deterministic replay fixtures and required cases

Six required deterministic cases (`docs/MILESTONES.md` B-M0-01 tests
requirement) live in `tests/replay/routing/cases/*.json` and are exercised by
`tests/path_b/routing/test_hard_constraint_audit.py` using a small,
test-local pure evaluator (not runtime code):

| Case | File | Demonstrates |
|---|---|---|
| Applicable closed edge | `cases/closed_edge.json` | A simulated active `StatusDecision`-style input excludes the route through it |
| Vehicle restriction | `cases/vehicle_restriction.json` | An HGV-only local control excludes `rigid_truck` but not `light_goods`/`emergency` |
| Direction restriction | `cases/direction_restriction.json` | A one-way hill band excludes the reverse direction only, and remains feasible forward despite `landslide_susceptibility: high` on the same band |
| Bridge/tunnel/access constraint | `cases/bridge_tunnel_access.json` | A low-clearance bridge excludes `rigid_truck` on three independent grounds and excludes `light_goods` on clearance alone, despite `light_goods` being under the weight and HGV limits |
| GraphHopper outage | `cases/graphhopper_outage.json` | Router unavailability returns a deterministic `502 upstream_unavailable`, with `route_feasible: null` — explicitly distinct from a hard-exclusion result |
| No verified feasible route | `cases/no_feasible_route.json` | Both candidate routes are hard-excluded simultaneously (closure on NH-27, unconfirmed-open HGV restriction on NH-6); explicit `no_verified_feasible_route` outcome, `routes: []`, non-empty `blocking_constraints` |

The direction-restriction case is the audit's explicit proof of ARCHITECTURE.md
D-007 ("no feasible verified route is a valid result" / "risk alone never
excludes a route"): the highest-risk band in the fixture (`landslide_susceptibility:
high`) is fully routable in its permitted direction.

## 5. Graph/extract checksum and provenance

| Field | Value |
|---|---|
| `graph_id` | `ner_lens_route_audit_fixture_v1` |
| File | `data/corridor/graphhopper/fixture_graph.v1.json` |
| SHA-256 | see `data/corridor/graphhopper/fixture_graph.v1.sha256` (recomputed by `tests/replay/routing/test_route_replay_fixtures.py::test_checksum_matches_recorded_provenance` on every test run) |
| Label | `synthetic_replay_fixture` |
| `is_real_osm_extract` | `false` |
| Real extract status | `not_yet_obtained` |

This checksum provenance covers the **audit fixture only**. It is not a
substitute for the real OSM extract checksum that A-M1-03 must record when
it imports actual `CorridorVersion`/`RoadSegment` data from a real Geofabrik
North-Eastern Zone download.

## 6. GraphHopper profile draft

`data/corridor/graphhopper/vehicle_profiles.yaml` documents the intended
`light_goods`, `rigid_truck`, and `emergency` profiles in a shape consistent
with GraphHopper's documented custom-model / vehicle-encoded-value approach
(GraphHopper profiles docs, cited in the source dossiers). This is
documentation for B-M1-02 to implement against; **no GraphHopper server
configuration was deployed or executed** as part of this task.

## 7. Known limitations (honest disclosure)

1. **No real OSM extract processed.** This is the largest gap. A-M1-03 must
   obtain and checksum a real Geofabrik North-Eastern Zone extract clipped to
   the 5 km route buffer before any live routability claim can be made.
2. **A-M0-01 has not published its corridor artifact.** This audit's
   corridor bounds, bands, and administrative-unit list are Path B's own
   reading of the source documents, not a confirmed `CorridorVersion`.
   Reconciliation is required (section 0).
3. **Heavy-vehicle/bridge/tunnel restriction data is mostly unknown, not
   verified-absent.** 8 of 10 fixture bands have unknown `maxheight_m`/
   `maxweight_t`; this mirrors the real, documented risk in
   `docs/RISKS_AND_DECISIONS.md` R-06 ("OSM lacks heavy-vehicle or structure
   restrictions").
4. **Turn restrictions are unaudited, not confirmed absent.** Every band
   currently lists an empty `turn_restrictions` array because no turn-
   restriction data source has been reviewed yet, not because none exist.
5. **NH-6 alternative surface/hazard data is largely `unverified`/`unknown`.**
   The alternative corridor has not received the same literature-based
   scrutiny as NH-27 in the source documents.
6. **No local driver or authority reviewer has been consulted** for this
   desk audit, contrary to `SIH-26002-TECH-STACK-IMPLEMENTATION-AND-VALIDATION.md`
   section 2's "two-day corridor audit" recommendation to "ask a local driver
   or authority reviewer to identify missing restrictions." This remains an
   open task, tracked here rather than silently skipped.
7. **Endpoint coordinates are approximate town-level coordinates**, not
   surveyed origin/destination points, and are labelled as such in
   `route-manifest.yaml`.

None of these limitations is treated as resolved. They are recorded so Sol
and Terra can assess whether they block P0.

## 8. Mapping to B-M0-01 acceptance criteria

| Acceptance criterion (MILESTONES.md) | Status |
|---|---|
| Topology, surface, bridge/tunnel, access, `maxheight`, `maxweight`, `hgv`, construction, turn and direction checks are recorded | Met, for the fixture graph — see section 3 table |
| One route is not removed by risk alone | Met — see the direction-restriction case and D-007 test |
| Missing legality data is visible | Met — `missing_legality_data` on every band, enforced by test |
| GraphHopper unavailability has a deterministic fixture path | Met — `graphhopper_outage.json` |
| Route fixture tests for closed edge, vehicle restriction, direction, and no-feasible-route | Met — 18 passing tests in `tests/replay/routing/` and `tests/path_b/routing/` |
| Checksum test for graph extract | Met for the **audit fixture**; real-extract checksum is deferred to A-M1-03 (see limitation 1) |

## 9. Completion condition and next dependency

Per `docs/MILESTONES.md`, B-M0-01's completion condition is: "route audit is
signed and labelled replay alternatives are available." The replay
alternatives are available now (section 4). The audit is **not yet signed**
in the Terra P0 sense: it requires (a) reconciliation with A-M0-01 once
published, and (b) Sol's review of the route contract per
`docs/ORCHESTRATION.md` section 6. This document records that the required
artifacts exist and are honest about their limitations; it does not itself
grant Terra P0.

**Exact next dependency for Path B:** `docs/decisions/corridor-audit.md`
(A-M0-01 output) and Sol's accepted M0 contract commit (`S-M0-01`) with
Terra P0 sign-off, before `B-M1-01` or `B-M1-02` may begin, per
`docs/ORCHESTRATION.md` section 13. This is a dependency gate, not a
user-approval gate, and is not bypassed by creating migrations or
alternative contracts.
