# B-M0-01 — Route and GraphHopper feasibility audit

**Status:** Path B corrective audit (post Terra P0 review), reconciled with
A-M0-01. Terra P0 remains **BLOCKED** per A's signed ledger — this is an
evidence-gap block, not a corridor rejection, and not yet a sign-off for
`B-M1-01`/`B-M1-02`.
**Owner:** Path B (Claude Sonnet 5)
**Branch / commit:** `path-b/m0-route-audit`, rebased onto `main` (Sol's
official SIH-26002 snapshot commit)
**Task:** `B-M0-01` per `docs/MILESTONES.md`
**Depends on (per MILESTONES.md):** `A-M0-01` draft corridor bounds and candidate endpoints — now available and reconciled.

## 0. Reconciliation status with A-M0-01 (read first)

**Reconciliation has now occurred.** This audit was diffed field-by-field
against A-M0-01's signed ledger at
`D:/SIH-2026/NER_LENS/.worktrees/path-a/docs/decisions/corridor-audit.md`.
Every reconciled field matched without disagreement:

| Field | A-M0-01 value | This document (after reconciliation) |
|---|---|---|
| Canonical corridor ID | `guwahati_silchar_nh27` | `guwahati_silchar_nh27` (`data/corridor/route-manifest.yaml`) |
| Six NH-27 audit bands | Jalukbari–Nagaon; Nagaon–Doboka; Doboka–Lanka–Lumding; Lumding–Maibang; Maibang–Harangajao/Balachera hill section; Balachera–Silchar | Same six bands, same order |
| NH-6 alternative hypothesis | "Candidate B — NH-6 direction via Meghalaya to Silchar," hypothesis only, no recommendation permitted | Same; labelled `guwahati_silchar_nh6` by Path B since A's ledger does not assign it a distinct slug |
| Route buffer | 5 km | 5 km |
| Hazard-context buffer | 20 km | 20 km |
| Administrative units | Kamrup Metropolitan, Nagaon, Hojai, Dima Hasao, Cachar | Same five |
| Replay/synthetic labelling | "Synthetic/replay reports visibly labelled; cannot validate ML"; every fixture must carry a `live_approved\|replay\|synthetic\|partner_dependent` label | This document's fixtures are labelled `synthetic_replay_fixture`; section 4 (real evidence) is labelled and separated from the synthetic fixture |
| Terra P0 status | `BLOCKED` — 7 named evidence gaps (route/restriction, authority, terms, labels, mission, policy owner) | Adopted as-is; Path B does not and cannot resolve items outside routing (authority, mission, terms) |

### Historical note (2026-09-10, initial draft — superseded)

At the time this document was first written, `docs/decisions/corridor-audit.md`
did not exist in the `path-a` worktree (verified at baseline commit `f6cfd51`:
no `docs/decisions/` or `data/` directory was present). This document used a
provisional corridor ID (`PROVISIONAL-guwahati-silchar-v0`) built directly
from the two primary SIH-26002 source documents and explicitly flagged
reconciliation as an open item. **That reconciliation has now occurred** (see
the table above); the historical note is preserved here for traceability
only and no longer describes the current state of this document.

## 1. What this audit is, and what it is not

This audit now has **two evidence layers**, kept clearly separate and never
conflated:

1. **A desk audit** of route feasibility and OSM-representable restriction
   coverage, built from named authority documents already cited in the
   source dossiers (NHAI section annexure, NHIDCL Assam corridors, the
   Parliamentary highway record, the PIB Mawlyngkhung–Panchgram approval)
   and peer-reviewed landslide-susceptibility literature for NH-27/NH-627
   and Dima Hasao, backed by a small, explicitly labelled **synthetic
   replay fixture graph** (`data/corridor/graphhopper/fixture_graph.v1.json`,
   `"label": "synthetic_replay_fixture"`, `"is_real_osm_extract": false`).
   Every band in that fixture records its citation basis and an honest
   `missing_legality_data` list. This exercises the hard-constraint policy's
   decision logic deterministically for every required category, including
   ones the real corridor extract does not currently exhibit (an active
   closure, a confirmed `hgv=NO`, a confirmed construction closure).
2. **A real evidence run** (added in this corrective audit, section 4a),
   performed once, outside the repository, in a non-runtime scratch
   sandbox: a real dated Geofabrik OSM extract was downloaded, imported
   into a real GraphHopper 11.0 instance, and queried for both candidates
   and two vehicle-profile proxies. Its bounded, checksummed results are
   committed under `data/corridor/graphhopper/real_evidence/`.

Neither layer is a claim that any specific restriction, current passability,
or legality has been confirmed for real-world use. Building and processing
the real North-Eastern Zone extract into stable operational segment IDs
inside the application, and wiring a live GraphHopper adapter into the
backend, remains **A-M1-03 / B-M1-02** scope, gated on Terra P0 and the
accepted M0 contract commit, per `docs/ORCHESTRATION.md` section 13 ("Do not
begin B-M1-01 or B-M1-02..."). This audit's real evidence run is a one-time,
non-runtime evidence-gathering exercise, not the backend routing adapter.

## 2. Candidate routes audited

See `data/corridor/route-manifest.yaml` for the machine-readable form.

| Route ID | Canonical ID (reconciled with A-M0-01) | Description | Role | Basis |
|---|---|---|---|---|
| `route_nh27_primary` | `guwahati_silchar_nh27` | Guwahati (Jalukbari) → Nagaon → Doboka → Lanka/Lumding → Maibang → Harangajao/Balachera hill section → Silchar, via NH-27 | Primary | NHAI annexure, NHIDCL Assam corridors, Parliamentary highway record |
| `route_nh6_alternative` | `guwahati_silchar_nh6` | Guwahati → Shillong → Jowai → Panchgram/Silchar, via NH-6 | Alternative | Source dossier; PIB Mawlyngkhung–Panchgram approval (planned-corridor context only) |

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
`data/corridor/graphhopper/vehicle_profiles.yaml`. As of this corrective
audit, `hard_constraints_checked` is **identical across all three profiles**
(topology, surface, bridge/tunnel/approach structure, access, `maxheight`,
`maxweight`, `hgv`, construction, turn restrictions, direction, and
planned-road exclusion) — every category is evaluated for every profile;
only the profile's own numeric limits and `hgv_exempt` flag change the
outcome. The previous version of this file under-listed light_goods'
checks even though the evaluator already excluded `light_goods` on
`maxheight_exceeded` in `cases/bridge_tunnel_access.json` — that
inconsistency was the Terra finding and is now corrected.

| Profile | max_weight_t | max_height_m | hgv_exempt | Notes |
|---|---:|---:|---|---|
| `light_goods` | 3.5 | 2.5 | yes | Least restricted |
| `rigid_truck` | 16.0 | 3.8 | no | Primary essential-medicine mission candidate profile |
| `emergency` | 7.5 | 3.0 | yes (traffic-control only) | Physical clearance/weight/construction/planned-road limits still apply — see ARCHITECTURE.md edge case "Emergency vehicle has legal exemption" |

The synthetic fixture graph now has 15 bands: the original 10 corridor
bands plus 5 dedicated `test_fixture_only` bands added in this corrective
audit, one per newly required executable-check category. Coverage summary:

| Category | Executable check now exists? | Fixture evidence |
|---|---|---|
| Topology (routable) | Yes — `test_topology_not_routable_is_a_hard_exclusion` | `band_test_disconnected_segment` (`topology_routable: false`) is excluded with `not_routable` |
| Surface, incl. explicit unknown | Yes — `test_surface_unverified_is_visible_not_excluded` | `band_alt_2_shillong_jowai` (`surface: "unverified"`) is disclosed in `missing_legality_data` and never produces a surface-named exclusion reason |
| Bridge/tunnel/approach structure | Yes — `test_bridge_structure_alone_is_not_a_hard_exclusion` (+ existing bridge/weight tests) | `band_test_clean_bridge` proves `segment_type: bridge` alone never excludes; `band_3_doboka_lanka_lumding` proves a *restricted* bridge does |
| Access restrictions | Yes — `test_access_denied_excludes_every_profile` | `band_test_private_access` (`access: "no"`, matching the real GraphHopper `road_access=NO` enum value confirmed in section 4a) excludes every profile |
| `maxheight`/`maxweight` | Yes — existing `bridge_tunnel_access` case | Excludes only the profiles whose own limit is exceeded |
| `hgv` | Yes — existing `vehicle_restriction` case | Excludes only non-exempt profiles |
| Confirmed construction restrictions | Yes — `test_confirmed_construction_excludes_every_profile` / `test_construction_false_is_not_excluded` | `band_test_confirmed_construction` (`construction: true`) excludes every profile; a band with `construction: false` is distinguished from one where construction is simply unaudited |
| Turn restrictions | Yes — `test_turn_restriction_blocks_only_its_direction` | `band_test_turn_restriction` blocks only the direction its restriction applies to |
| Direction restrictions | Yes — existing `direction_restriction` case | Blocks only the disallowed direction, proven independent of risk |
| Planned/unopened-road exclusion | Yes — `test_planned_unopened_road_excludes_every_profile_even_hgv_exempt_ones` | `band_alt_2_shillong_jowai.planned_unopened=true` excludes every profile, including `hgv_exempt` ones, regardless of any other tag |
| Unknown legality never becomes closure | Yes — `test_unknown_fields_never_become_hard_exclusion` (regression) | `band_1_jalukbari_nagaon` has unknown `maxheight_m`/`maxweight_t`/`hgv` for every profile and is fully feasible for all of them |
| Coverage-state conservative signal | Yes — `test_coverage_state_flags_missing_data_without_excluding` | Bands with any `missing_legality_data` report `coverage_state="insufficient_evidence"`, a visible label, never a silent exclusion and never a silent "confirmed open" |

This table is the audit's answer to "missing legality data must be visible":
most heavy-vehicle structural limits along the NH-27/NH-6 corridor bands
are unknown, not zero, and are now proven — by an executable regression
test, not only by data presence — never to silently become a confirmed
closure.

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
| No verified feasible route | `cases/no_feasible_route.json` | Both candidate routes are hard-excluded simultaneously (closure on NH-27; HGV restriction, confirmed construction, and planned-road exclusion on NH-6); explicit `no_verified_feasible_route` outcome, `routes: []`, non-empty `blocking_constraints` |

The direction-restriction case is the audit's explicit proof of ARCHITECTURE.md
D-007 ("no feasible verified route is a valid result" / "risk alone never
excludes a route"): the highest-risk band in the fixture (`landslide_susceptibility:
high`) is fully routable in its permitted direction. 12 more tests were added
in this corrective audit for the categories listed in section 3; the full
suite is 28 tests, all passing.

## 4a. Real OSM extract and GraphHopper evidence (corrective-audit addition)

Per the corrective-audit instruction, this session **attempted, and
obtained, real evidence** in a bounded, non-runtime scratch sandbox outside
this repository and outside any Path A/B/Sol worktree
(`D:/SIH-2026/.m0-graph-sandbox/`, deleted after evidence was extracted).
Bounded, committed evidence lives in `data/corridor/graphhopper/real_evidence/`:

| File | Contents |
|---|---|
| `real_extract_provenance.yaml` | OSM extract source URL, licence, retrieval time, byte size, MD5 (Geofabrik-published, verified to match) and SHA-256 (computed); GraphHopper release provenance and SHA-256; exact query parameters used |
| `real_route_results_summary.json` | Per route/profile distance, time, and aggregated `path_details` value counts (no full geometry) |
| `graphhopper-config.yml`, `my_car.json`, `my_truck.json` | The exact GraphHopper config and *official, unmodified* GraphHopper example custom models used (renamed only to avoid a built-in-name collision) |
| `REPRODUCE.md` | Exact commands to reproduce the run |

### What was actually done

1. Downloaded `https://download.geofabrik.de/asia/india/north-eastern-zone-260909.osm.pbf` (109,305,518 bytes; OSM data as of `2026-09-09T20:21:20Z`; ODbL licence). MD5 matched Geofabrik's published `.md5` exactly (`eee3d24fe21d7be1d1b4f01603979273`); SHA-256 computed locally (`9250938d...c068a9`, full value in `real_extract_provenance.yaml`).
2. Downloaded the official GraphHopper 11.0 release jar from GitHub Releases (not a third-party Docker image) and the official `car.json`/`truck.json` example custom models from the same tagged source tree.
3. Ran GraphHopper 11.0 in an official `eclipse-temurin:21-jre-jammy` container, importing the real extract with `graph.encoded_values: road_access, car_access, car_average_speed, hgv, max_width, max_height, max_weight, max_weight_except`. Import completed in under 30 seconds; `GET /info` confirmed `data_date: "2026-09-09T20:21:20Z"`, matching the Geofabrik page exactly, and confirmed all the required encoded values (including `road_environment` with `BRIDGE`/`TUNNEL`/`FORD` values and `road_class` with a `CONSTRUCTION` value) are natively present in this GraphHopper version.
4. Queried both candidates (`route_nh27_primary` direct; `route_nh6_alternative` biased via Shillong/Jowai waypoints — GraphHopper has no "named highway" query mode) for the `car` (light_goods/emergency proxy) and `truck` (rigid_truck proxy) profiles, requesting `road_environment`, `road_access`, `road_class`, `max_height`, `max_weight`, `hgv` path details.

### Real findings

| Query | Distance | Time | `road_environment` | `hgv` | `max_height`/`max_weight` |
|---|---:|---:|---|---|---|
| NH-27, car | 298.6 km | 4h25m | 37 bridge, 1 tunnel segments | missing (entire route) | unset (entire route) |
| NH-27, truck | 302.5 km | 4h53m | 38 bridge, 1 tunnel segments | missing (entire route) | unset (entire route) |
| NH-6 (via Shillong/Jowai), car | 307.3 km | 4h38m | 36 bridge, 1 tunnel, 1 ford | missing (entire route) | unset (entire route) |
| NH-6 (via Shillong/Jowai), truck | 309.4 km | 5h07m | 37 bridge, 1 tunnel, 1 ford | missing (entire route) | unset (entire route) |

**Both candidates are topologically routable end-to-end in a real, dated
OSM extract, for both a car-class and a truck-class GraphHopper profile.**
This directly answers MILESTONES.md's "both candidates are routable" audit
question with a real result rather than a desk assumption. The desk audit's
prediction — that heavy-vehicle legality tags (`hgv`, `maxheight`,
`maxweight`) are essentially absent from OSM for this corridor — is now a
**measured finding**, not an assumption: `hgv` was `missing` and
`max_height`/`max_weight` were unset for the entirety of every returned
path on both candidates. No `road_class=CONSTRUCTION` segment was
encountered on either returned path.

### Honest limitations of the real run

- `light_goods` and `emergency` were **not** separately modelled as real
  GraphHopper custom profiles; only the official `car` and `truck` example
  models were used, with `car` standing in for both. Authoring
  project-specific custom models carrying the exact `vehicle_profiles.yaml`
  numeric limits is real follow-on work, not done here.
- The NH-6 query used via-points to bias GraphHopper's shortest/fastest
  path onto the Shillong/Jowai corridor; GraphHopper computed its own
  optimal path between those points, which is not the same as confirming
  a specific named highway's continuity.
- No turn-restriction data was extracted from the real graph (GraphHopper's
  path-details API does not expose turn-cost tables); this remains
  desk/fixture-only evidence (section 3).
- This was a single run against a single dated extract; it does not
  establish ongoing monitoring, a checksummed operational graph version, or
  A-M1-03's stable internal segment IDs.
- The scratch sandbox (jar, PBF, generated graph cache) was deleted after
  evidence extraction, per instruction not to commit large/generated
  binaries; it is fully reproducible from `REPRODUCE.md` and the recorded
  checksums.

## 5. Graph/extract checksum and provenance

| Field | Value |
|---|---|
| `graph_id` | `ner_lens_route_audit_fixture_v1` (synthetic fixture) |
| File | `data/corridor/graphhopper/fixture_graph.v1.json` |
| SHA-256 | see `data/corridor/graphhopper/fixture_graph.v1.sha256` (recomputed by `tests/replay/routing/test_route_replay_fixtures.py::test_checksum_matches_recorded_provenance` on every test run) |
| Label | `synthetic_replay_fixture` |
| `is_real_osm_extract` | `false` |
| Real extract SHA-256 (section 4a) | `9250938dd6e8c61ad3ca533620a86c5d286e86f60c2bc45086e173f2ace068a9` (`north-eastern-zone-260909.osm.pbf`, OSM data as of `2026-09-09T20:21:20Z`) |

The fixture checksum and the real-extract checksum are recorded separately
and are not substitutes for each other. Neither is a substitute for the
operational graph-version checksum A-M1-03/B-M1-02 must record when the
backend imports a graph for real.

## 6. GraphHopper profile draft

`data/corridor/graphhopper/vehicle_profiles.yaml` documents the intended
`light_goods`, `rigid_truck`, and `emergency` profiles in a shape consistent
with GraphHopper's documented custom-model / vehicle-encoded-value approach.
Section 4a's real run confirms this shape works against a real GraphHopper
11.0 instance for the `car`/`truck` proxies. Authoring the exact
`light_goods`/`emergency` numeric custom models, and wiring any of this into
the backend, remains B-M1-02 scope; **no backend GraphHopper adapter was
implemented** as part of this task.

## 7. Known limitations (honest disclosure, updated)

1. **RESOLVED — a real OSM extract was processed** (section 4a). What
   remains open: A-M1-03 must still import a graph into the *backend's*
   operational schema with stable internal segment IDs; this audit's real
   run proves the extract and GraphHopper mechanics work, not that the
   backend integration is done.
2. **RESOLVED — A-M0-01 has published its corridor artifact and this
   document is reconciled with it** (section 0).
3. **CONFIRMED, not merely assumed — heavy-vehicle/bridge/tunnel
   restriction data is absent from OSM for this corridor.** Section 4a's
   real run measured `hgv=missing` and `max_height`/`max_weight` unset
   along the entire returned path for both candidates. This still mirrors
   `docs/RISKS_AND_DECISIONS.md` R-06, now with real evidence instead of a
   desk assumption.
4. **Turn restrictions remain unaudited against real data**, though an
   executable check now exists against the synthetic fixture (section 3).
   Extracting real turn-restriction/turn-cost data was out of scope for
   this bounded evidence run (GraphHopper's `/route` path-details API does
   not expose it).
5. **NH-6 alternative surface/hazard data remains largely
   `unverified`/`unknown`** in the desk audit; the real run confirms
   topological routability but does not resolve surface quality.
6. **No local driver or authority reviewer has been consulted.** Still
   open; outside Path B's ownership (see the human/partner evidence list
   at the end of this document).
7. **Endpoint coordinates are approximate town-level coordinates**, not
   surveyed origin/destination points, in both the desk audit and the real
   run's query parameters.
8. **`light_goods`/`emergency` were not separately modelled in the real
   GraphHopper run** (section 4a); only `car`/`truck` proxies were queried.

Limitations 1 and 2 are resolved by this corrective audit. The remainder
are recorded so Sol and Terra can assess whether they still block P0 —
and per A-M0-01's signed ledger, several of them (named authority, reviewer,
mission owner, policy thresholds) are outside Path B's ownership and remain
blocking regardless of routing evidence.

## 8. Mapping to B-M0-01 acceptance criteria

| Acceptance criterion (MILESTONES.md) | Status |
|---|---|
| Topology, surface, bridge/tunnel, access, `maxheight`, `maxweight`, `hgv`, construction, turn and direction checks are recorded | Met — executable checks for every category, both against the synthetic fixture (section 3) and, for topology/hgv/maxheight/maxweight/bridge presence, against real data (section 4a) |
| One route is not removed by risk alone | Met — direction-restriction case and D-007 regression test |
| Missing legality data is visible | Met — `missing_legality_data`/`coverage_state` on every band, enforced by test; confirmed against real data in section 4a |
| GraphHopper unavailability has a deterministic fixture path | Met — `graphhopper_outage.json` |
| Route fixture tests for closed edge, vehicle restriction, direction, and no-feasible-route | Met — 28 passing tests in `tests/replay/routing/` and `tests/path_b/routing/` |
| Checksum test for graph extract | Met for the **synthetic audit fixture** (enforced by test) and recorded (not test-enforced, since the binary is not committed) for the **real extract** in section 4a/5 |
| Both candidates are routable, or an explicit rejection is recorded | Met with real evidence — both candidates returned real HTTP 200 routes in GraphHopper 11.0 against the real dated extract (section 4a) |

## 9. Completion condition, Terra P0 status, and next dependency

Per `docs/MILESTONES.md`, B-M0-01's completion condition is: "route audit is
signed and labelled replay alternatives are available." The replay
alternatives are available (section 4), reconciliation with A-M0-01 is done
(section 0), and real routing evidence now exists (section 4a). **This audit
is not itself a Terra P0 sign-off** — Terra P0 is a cross-path gate, and
A-M0-01's own signed ledger records it as `BLOCKED` for reasons entirely
outside Path B's ownership: no named status authority, no evidence reviewer,
no mission owner, no source-terms approval, no positive-event/ground-truth
ledger, and no operational-owner-approved policy thresholds. Path B's route
and restriction evidence does not and cannot resolve those items.

**Terra P0 can be rerun for the routing/restriction-evidence portion of its
scope**, since the two items previously blocking that portion — corridor
reconciliation and real graph/GraphHopper evidence — are now resolved. Terra
P0 as a whole remains blocked pending the human/partner evidence listed
below, which is not a Path B deliverable.

**Exact next dependency for Path B:** Sol's accepted M0 contract commit
(`S-M0-01`) with Terra P0 sign-off across *all* M0 tracks (A, B, and the
human/partner items below), before `B-M1-01` or `B-M1-02` may begin, per
`docs/ORCHESTRATION.md` section 13. This is a dependency gate, not a
user-approval gate, and is not bypassed by creating migrations or
alternative contracts.

### Human/partner evidence still required (outside Path B's ownership)

Per A-M0-01's P0 decision record and this corrective audit's own findings,
these remain unavoidable and are not resolvable by further routing/graph
work:

- a named operational status authority (e.g. NHIDCL/NHAI corridor
  operations, Assam PWD/ASDMA, or a district authority) with jurisdiction
  and expiry decision rights;
- a named evidence reviewer with scope and conflict-resolution authority;
- a named essential-medicine mission owner and GPS/field consent basis, or
  a Sol/human-signed replay-only mission boundary;
- source access/terms approval for IMD, GSI, CWC, ASDMA, SACHET, and any
  other live source, with permitted replay fallbacks recorded;
- a permitted positive-event and passability/ground-truth ledger path with
  reviewer adjudication;
- Sol/operational-owner approval of `RouteVerificationPolicy` inputs: graph
  currency rule, source-specific maximum ages, minimum evidence coverage,
  and the degraded-recommendation rule.
