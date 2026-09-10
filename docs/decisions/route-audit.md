# B-M0-01 — Route and GraphHopper feasibility audit

**Status:** Path B second corrective audit (post second Terra P0 review).
Overall Terra P0 remains **BLOCKED** for reasons entirely outside Path B's
ownership (see section 9). The **routing sub-gate**, which was separately
BLOCKED for using generic car/truck profiles and carrying a timestamp
inconsistency, is corrected in this revision: the exact three project
vehicle profiles were run against a real graph for both route hypotheses,
with independently-captured timestamps and checksummed receipts. This is
not yet a sign-off for `B-M1-01`/`B-M1-02`.
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

## 4a. Real OSM extract and GraphHopper evidence (second corrective audit — v2, current)

**v1 (`data/corridor/graphhopper/real_evidence/v1_superseded/`) is
superseded.** Terra's second review found two defects: a timestamp
inconsistency (an HTTP proxy `Date` header was recorded as if it were the
retrieval time) and the use of generic `car`/`truck` example profiles
instead of the three exact project profiles. Both are corrected below; see
`v1_superseded/SUPERSEDED.md` for the full explanation. **v2
(`data/corridor/graphhopper/real_evidence/v2/`) is the current,
authoritative real-evidence layer.**

### Boundary statement

This is real, one-time evidence gathering performed in a bounded, non-
runtime scratch sandbox outside this repository and outside any Path
A/B/Sol worktree (`D:/SIH-2026/.m0-graph-sandbox2/`, deleted after evidence
extraction). It is not a running service, not the backend routing adapter,
and no route in it is operationally verified — GraphHopper returning
HTTP 200 means the graph and encoded vehicle constraints permit a path; it
is not an authorized operational status and not a `RouteVerificationPolicy`
outcome. The tests in `tests/path_b/routing/test_real_evidence_receipts.py`
validate the **committed receipt files**, not a live server.

### Timestamp methodology (correcting the v1 defect)

v1 recorded an HTTP response `Date` header (`04:36:50Z`) as the retrieval
time, which conflicted with a separately-worded "completed by 04:08 local"
note. Root cause: Geofabrik serves the PBF through a caching proxy; on a
cache hit, the `Date` header reflects when the cached response was
generated, not when this session retrieved it — proven by an `Age: 17387`
header (≈4.8 hours) on the repeat request in v2. v2 uses this session's own
shell clock (`date -u`), captured immediately before and after every
network call, as the sole authoritative timestamp source; HTTP headers are
recorded for transparency only and explicitly labelled non-authoritative.
See `real_extract_provenance.yaml`'s `TIMESTAMP METHODOLOGY` header comment
and `osm_extract.retrieval_timestamps_utc`/`http_response_headers_informational_only`.

### What was actually done

1. Re-downloaded the same dated extract, `north-eastern-zone-260909.osm.pbf`
   (109,305,518 bytes; OSM data as of `2026-09-09T20:21:20Z`; ODbL). Byte
   size, MD5 (`eee3d24f...79273`), and SHA-256
   (`9250938d...ce068a9`) are identical to v1, confirming no upstream
   change. **Retained outside git** at
   `D:\SIH-2026\NER_LENS_ARTIFACTS\m0\north-eastern-zone-260909.osm.pbf`;
   hash re-verified after the route run (identical).
2. Re-downloaded the same official GraphHopper 11.0 release jar
   (SHA-256 `b59c024a...f613def`, identical to v1).
3. Authored three **project-specific** custom models
   (`light_goods.json`, `rigid_truck.json`, `emergency.json`) using the
   exact numeric limits from `data/corridor/graphhopper/vehicle_profiles.yaml`
   (3.5t/2.5m, 16.0t/3.8m, 7.5t/3.0m). `rigid_truck.json` adapts
   GraphHopper's official `truck.json` example with this project's own
   thresholds substituted for its hard-coded 18t/4m. `emergency.json`
   grants **no invented legal exemption**: it enforces `road_access`,
   `max_height`, and `max_weight` identically to `light_goods`, because this
   GraphHopper run has no encoded value representing a time-window/convoy
   control — the only kind of exemption `vehicle_profiles.yaml` documents as
   possibly applicable to emergency vehicles.
4. Ran GraphHopper 11.0 (official `eclipse-temurin:21-jre-jammy` container)
   with all three profiles under CH preparation (`rigid_truck` is
   edge-based, due to `turn_costs`, and took ~80s to prepare — noticeably
   longer than the two node-based profiles). `GET /info` confirmed
   `data_date: "2026-09-09T20:21:20Z"` and all three profile names present.
5. Queried **both route hypotheses × all three profiles** (6 combinations)
   with `instructions=true` and `details` for `road_environment`,
   `road_access`, `road_class`, `max_height`, `max_weight`, `hgv`. `route_nh27_primary`
   is a direct origin→destination query (no via-points). `route_nh6_alternative`
   is **explicitly waypoint-biased** through Shillong (`25.5788,91.8933`)
   and Jowai (`25.4340,92.1935`) — GraphHopper has no "follow this named
   highway" query mode.

### Real findings

| Query | Distance | Time | `road_environment` | `hgv` | `max_height`/`max_weight` | Named "NH6"? |
|---|---:|---:|---|---|---|---|
| NH-27, light_goods | 298.6 km | 4h25m | 39 road/37 bridge/1 tunnel | missing | unset | no |
| NH-27, rigid_truck | 302.5 km | 4h53m | 40 road/38 bridge/1 tunnel | missing | unset | no |
| NH-27, emergency | 299.8 km | 4h24m | 40 road/38 bridge/1 tunnel | missing | unset | no |
| NH-6, light_goods | 307.3 km | 4h38m | 41 road/36 bridge/1 tunnel/1 ford | missing | unset | **yes** |
| NH-6, rigid_truck | 309.4 km | 5h07m | 42 road/37 bridge/1 tunnel/1 ford | missing | unset | **yes** |
| NH-6, emergency | 308.6 km | 4h36m | 42 road/37 bridge/1 tunnel/1 ford | missing | unset | **yes** |

**All three exact project profiles returned real HTTP 200 routes for both
route hypotheses.** `hgv` and `max_height`/`max_weight` remain measured as
missing/unset for the entire returned path on every single query — the
same finding as v1, now confirmed with the project's own exact profiles
rather than generic proxies. No `road_class=CONSTRUCTION` segment and no
routing warnings/errors were encountered on any of the six queries.

**Road-name evidence, asymmetric between the two candidates (Terra's
explicit ask):** none of the three NH-27 queries' `instructions[].street_name`
values matched "NH27"/"NH-27"/"National Highway 27" — the 8 unique named
streets returned are all local Guwahati-area roads (e.g. "Zoo Road",
"Kahilipara Road"). This is not strong evidence *against* NH-27 identity:
Indian national-highway ways very often carry only an OSM `ref` tag (e.g.
`ref=NH27`) without a `name` tag, and GraphHopper's `street_name` reflects
`name`, not `ref`; this API surface does not expose `ref`. By contrast, the
literal string **"NH6" appears as a `street_name`** in all three NH-6
queries' instructions — direct (though single-segment) OSM-tag evidence
that the waypoint-biased path traverses at least one way explicitly named
"NH6", which is stronger direct naming evidence than NH-27 currently has
from this API surface, precisely because NH-6's route was waypoint-biased
through towns close to that segment. Neither finding confirms full
end-to-end continuity along either named highway; both routes' real
identity rests on the desk audit's NHAI/NHIDCL/Parliamentary citations plus
this endpoint/via-point selection, not on an automated ref/name match for
every edge.

### Committed receipts (`data/corridor/graphhopper/real_evidence/v2/`)

| File | Contents |
|---|---|
| `real_extract_provenance.yaml` | Full provenance: extract/jar/retention hashes, timestamp methodology, per-profile custom-model hashes, per-query request parameters and via-points, real findings, honest limitations |
| `raw_info.json` | Raw `GET /info` response |
| `raw_responses/*.json` (6 files) | Raw, unmodified `GET /route` responses, one per route×profile combination, including full geometry and turn-by-turn instructions |
| `response_index.json` | Maps each query to its exact request parameters, response file, and SHA-256 |
| `result_summary.json` | Per-query distance/time/street-names/path-details aggregation |
| `graphhopper-config.yml`, `light_goods.json`, `rigid_truck.json`, `emergency.json` | Exact config and exact project-specific custom models used |
| `query_timestamps.log` | Independently captured before/after shell-clock timestamp for every query |
| `REPRODUCE.md` | Exact commands to reproduce the run |

Every raw response's SHA-256 is recorded in both `real_extract_provenance.yaml`
and `response_index.json`; `result_summary.json` and `response_index.json`
are themselves hashed in `real_extract_provenance.yaml`
(`result_summary_sha256`, `response_index_sha256`). All of this is enforced
by `tests/path_b/routing/test_real_evidence_receipts.py`.

### Honest limitations of the real run (v2)

- Corridor identity is established by origin/destination/via-point
  selection plus desk-audit citations, not by an automated OSM ref/name
  match for every edge — see the road-name evidence above.
- `route_nh6_alternative` remains explicitly waypoint-biased; GraphHopper
  computed its own optimal sub-path between each consecutive waypoint pair.
- No turn-restriction data was extracted from the real graph (GraphHopper's
  `/route` path-details API does not expose turn-cost tables); this remains
  desk/fixture-only evidence (section 3).
- This is a single run against a single dated extract on 2026-09-10. It
  does not establish ongoing monitoring, a checksummed *operational* graph
  version, or A-M1-03's stable internal segment IDs.
- The retained PBF, jar, and generated GraphHopper cache are not committed
  to git; only the receipts above are. The scratch sandbox
  (`D:/SIH-2026/.m0-graph-sandbox2/`) was deleted after evidence extraction;
  the dated PBF is retained separately at
  `D:\SIH-2026\NER_LENS_ARTIFACTS\m0\` and its hash was verified identical
  both before and after the route run.
- No route in this evidence is operationally verified; see the boundary
  statement above.

## 5. Graph/extract checksum and provenance

| Field | Value |
|---|---|
| `graph_id` | `ner_lens_route_audit_fixture_v1` (synthetic fixture) |
| File | `data/corridor/graphhopper/fixture_graph.v1.json` |
| SHA-256 | see `data/corridor/graphhopper/fixture_graph.v1.sha256` (recomputed by `tests/replay/routing/test_route_replay_fixtures.py::test_checksum_matches_recorded_provenance` on every test run) |
| Label | `synthetic_replay_fixture` |
| `is_real_osm_extract` | `false` |
| `real_osm_extract_status` | `obtained_separately_not_merged_into_this_synthetic_fixture` (corrected in the second corrective audit — see section 4a; this fixture is deliberately never merged with real data so the two evidence layers cannot be confused) |
| Real extract SHA-256 (section 4a) | `9250938dd6e8c61ad3ca533620a86c5d286e86f60c2bc45086e173f2ace068a9` (`north-eastern-zone-260909.osm.pbf`, OSM data as of `2026-09-09T20:21:20Z`) |
| Retained PBF path | `D:\SIH-2026\NER_LENS_ARTIFACTS\m0\north-eastern-zone-260909.osm.pbf` (outside git; hash verified before and after the route run) |

The fixture checksum and the real-extract checksum are recorded separately
and are not substitutes for each other. Neither is a substitute for the
operational graph-version checksum A-M1-03/B-M1-02 must record when the
backend imports a graph for real.

## 6. GraphHopper profile draft

`data/corridor/graphhopper/vehicle_profiles.yaml` documents the
`light_goods`, `rigid_truck`, and `emergency` profiles. Section 4a's second
real run confirms this shape works against a real GraphHopper 11.0 instance
using **project-specific custom models with the exact numeric limits**
(`data/corridor/graphhopper/real_evidence/v2/{light_goods,rigid_truck,emergency}.json`),
not generic proxies. Wiring any of this into the backend remains B-M1-02
scope; **no backend GraphHopper adapter was implemented** as part of this
task.

## 7. Known limitations (honest disclosure, updated after the second corrective audit)

1. **RESOLVED — a real OSM extract was processed**, twice, most recently
   with the three exact project vehicle profiles (section 4a). What remains
   open: A-M1-03 must still import a graph into the *backend's* operational
   schema with stable internal segment IDs; this audit's real run proves
   the extract and GraphHopper mechanics work, not that the backend
   integration is done.
2. **RESOLVED — A-M0-01 has published its corridor artifact and this
   document is reconciled with it** (section 0).
3. **RESOLVED — the exact three project vehicle profiles were run**, not
   generic car/truck proxies, with no invented emergency legal exemption
   (section 4a).
4. **RESOLVED — the timestamp inconsistency in the first real run** (an
   HTTP proxy `Date` header treated as retrieval time) is corrected; v2 uses
   independently captured shell-clock timestamps with an explicit
   methodology note (section 4a).
5. **CONFIRMED, not merely assumed, by two independent real runs —
   heavy-vehicle/bridge/tunnel restriction data is absent from OSM for this
   corridor.** `hgv=missing` and `max_height`/`max_weight` unset along the
   entire returned path, for both candidates and now all three exact
   profiles. This mirrors `docs/RISKS_AND_DECISIONS.md` R-06 with real,
   repeated measurement.
6. **Turn restrictions remain unaudited against real data**, though an
   executable check now exists against the synthetic fixture (section 3).
   GraphHopper's `/route` path-details API does not expose turn-cost
   tables; extracting this would require a different tool (e.g. inspecting
   the graph's turn-cost storage directly), out of this bounded scope.
7. **NH-6 continuity is confirmed only at one segment by a real "NH6"
   OSM name tag; NH-27 has no equivalent real name-tag match** in the
   returned path's instructions (section 4a road-name evidence). Neither
   route's full end-to-end continuity along its named highway is confirmed
   edge-by-edge; both rest on endpoint/via-point selection plus the desk
   audit's authority citations.
8. **NH-6 alternative surface/hazard data remains largely
   `unverified`/`unknown`** in the desk audit; the real run confirms
   topological routability but does not resolve surface quality.
9. **No local driver or authority reviewer has been consulted.** Still
   open; outside Path B's ownership (see the human/partner evidence list
   at the end of this document).
10. **Endpoint/via-point coordinates are approximate town-level
    coordinates**, not surveyed points, in both the desk audit and the real
    run's query parameters.

Limitations 1-4 are newly resolved by this second corrective audit. The
remainder are recorded so Sol and Terra can assess whether they still block
P0 — and per A-M0-01's signed ledger, several (named authority, reviewer,
mission owner, policy thresholds) are outside Path B's ownership and remain
blocking regardless of routing evidence.

## 8. Mapping to B-M0-01 acceptance criteria

| Acceptance criterion (MILESTONES.md) | Status |
|---|---|
| Topology, surface, bridge/tunnel, access, `maxheight`, `maxweight`, `hgv`, construction, turn and direction checks are recorded | Met — executable checks for every category against the synthetic fixture (section 3), and topology/hgv/maxheight/maxweight/bridge/tunnel/ford presence confirmed against real data for all three exact profiles (section 4a) |
| One route is not removed by risk alone | Met — direction-restriction case and D-007 regression test |
| Missing legality data is visible | Met — `missing_legality_data`/`coverage_state` on every band, enforced by test; confirmed against real data (twice) in section 4a |
| GraphHopper unavailability has a deterministic fixture path | Met — `graphhopper_outage.json` |
| Route fixture tests for closed edge, vehicle restriction, direction, and no-feasible-route | Met — 28 passing tests in `tests/replay/routing/` and `tests/path_b/routing/`, plus 20 real-evidence-receipt tests |
| Checksum test for graph extract | Met for the **synthetic audit fixture** (enforced by test) and for the **real extract** — retained PBF hash verified before and after the route run, recorded in provenance and enforced by `test_pbf_hash_recorded_in_provenance_matches_retention_record` |
| Both candidates are routable, or an explicit rejection is recorded | Met with real evidence — both candidates returned real HTTP 200 routes for all three exact profiles in GraphHopper 11.0 against the real dated extract (section 4a) |

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

**The routing sub-gate is ready for Terra to rerun.** Its two named defects
— generic car/truck profiles instead of the three exact project profiles,
and the timestamp inconsistency in the real-evidence provenance — are both
corrected in section 4a with committed, checksummed, independently
verifiable receipts. Terra P0 **as a whole** remains blocked pending the
human/partner evidence listed below, which is not resolvable by further
routing/graph work and is not a Path B deliverable.

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
