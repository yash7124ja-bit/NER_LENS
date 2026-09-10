# A-M0-01 corridor, source, and label feasibility ledger

**Audit date:** 2026-09-10 (Asia/Calcutta)
**Owner:** Path A (GPT-5.6 Luna)
**Reviewer:** Sol (pending review)
**Gate:** Terra P0 (not passed; routing sub-gate PASS only)
**Status:** `BLOCKED — provisional corridor retained; runtime work must not start`

This is an evidence ledger, not a route or model result. A fact is marked
`verified` only when the linked page was opened during this audit or the fact is
explicitly present in the local control documents. `assumption`, `inaccessible`,
`replay`, and `partner-dependent` are never promoted to verified facts.

## 1. Decision summary

| Item | Decision | Evidence state |
|---|---|---|
| Working corridor | Keep `guwahati_silchar_nh27` as a provisional hypothesis | A bounded real probe returned a path between approximate Guwahati/Silchar points; no operational graph or legality approval |
| Candidate alternative | Keep `guwahati_silchar_nh6` via Shillong–Jowai–Panchgram/Silchar as a hypothesis | Three exact-profile queries returned paths; NH-6 remains waypoint-biased and current-access/construction/legality review is open |
| Routability | **Routing sub-gate PASS — bounded evidence only** | Path B v3 provides 27 checksummed receipts for all three exact profiles, including the six-band NH-27 candidate and NH-6 alternative; this does not authorize M1 |
| Restriction audit | **Partial real evidence; operational restriction audit remains open** | v3 records mixed road refs, hard-exclusion model rules, bridge/tunnel/ford observations, and hill-band preference divergence; turn/detail, current legality, authority, and status remain unresolved |
| Operational status authority | **Unassigned** | `district_officer` is a contract role, not a named authority or partner |
| Evidence reviewer | **Unassigned** | ASDMA/NHAI/NHIDCL contacts are outreach candidates only, not approvals |
| Positive-event path | **Candidate sources identified; label ledger absent** | GSI/ASDMA/CWC/SACHET/authority reports need segment/time/review validation |
| Mission | Synthetic essential-medicine mission hypothesis only | No partner, consent, vehicle, or live GPS evidence |
| Route policy | Conservative unresolved policy | Numeric age/coverage thresholds and approving owner are not available |

**Routing sub-gate conclusion:** Terra's bounded routing verdict is PASS at
Path B commit `42c9205`. Dated 2026-09-09 OSM plus GraphHopper 11 represents
all six audit-band endpoints for all three profiles, with mixed road refs,
hill-band preference divergence, and NH-6 waypoint bias. This establishes no
current passability, legal, status, or recommendation claim, and the routing
sub-gate PASS does not authorize M1.

**P0 conclusion:** Do not begin A-M1-01. Terra P0 cannot sign this audit until
the remaining operational graph/segment and restriction evidence, plus the
authority, terms, label, mission, and policy-owner evidence, is supplied. This
is an explicit stop/redirect outcome, not a claim that either candidate is
infeasible.

## 2. Candidate corridor hypotheses

### Candidate A — NH-27 Guwahati–Silchar

The local technical blueprint names the chain as Guwahati/Jalukbari–Nagaon,
Nagaon–Doboka, Doboka–Lanka–Lumding, Lumding–Maibang,
Maibang–Harangajao/Balachera, and Balachera–Silchar. NHIDCL's Assam page,
retrieved 2026-09-10, lists `Daboka-Lahorijan` and `Balachera - Harangajao
NH-27(New)` among Assam corridors. That verifies that the official page contains
related corridor project entries. Path B's v3 bounded real probe represents all
six audit-band endpoints for all three exact profiles, using a labelled direct
control, a threaded band query, and independent per-band legs. Its NH-27
candidate is a mixed road-ref result, not a single named highway; it does
**not** verify current passability, legal access, status, or recommendation.
The NHAI annexure URL listed by the blueprint was not
retrievable in the research browser.

**Route status:** bounded mixed-road evidence; provisional hypothesis; no
current passability/legal/status/recommendation claim permitted.

### Candidate B — NH-6 direction via Meghalaya to Silchar

The local technical blueprint proposes the Guwahati–Shillong–Jowai–Panchgram/
Silchar direction via NH-6 as an alternative. Path B used Shillong and Jowai
waypoints to bias GraphHopper toward this hypothesis; that is not confirmation
that the named highway is continuous or currently usable. A project approval or
strategic connection is not evidence that a road is presently routable. Planned
or under-construction infrastructure must not be inserted as an open edge.

**Route status:** waypoint-biased query path only; provisional hypothesis; no
current passability/legal/status/recommendation claim permitted.

## 3. Six audit bands and geometry status

These are named audit bands from the technical blueprint. Path B v3 now
represents every band endpoint for all three exact profiles with independent
leg receipts and a threaded consistency check. The results are still not
operational segment records: internal IDs, authority, chainage, and backend
graph-edge mapping remain unassigned.

| Band | Name | Required graph check | Current state |
|---:|---|---|---|
| 1 | Guwahati/Jalukbari–Nagaon | primary/alternative edge mapping and access | `bounded v3 receipt; mixed refs; no operational IDs` |
| 2 | Nagaon–Doboka | road class, construction, direction | `bounded v3 receipt; mixed refs; no operational IDs` |
| 3 | Doboka–Lanka–Lumding | vehicle restrictions and alternate edge mapping | `bounded v3 receipt; mixed refs; no operational IDs` |
| 4 | Lumding–Maibang | hill-road topology, surface, bridge constraints | `bounded v3 receipt; mixed refs; no operational IDs` |
| 5 | Maibang–Harangajao/Balachera hill section | bridge/tunnel, `maxweight`, `maxheight`, `hgv`, construction | `bounded v3 receipt; profile preference divergence; no operational IDs` |
| 6 | Balachera–Silchar | final approach, access and authority boundary | `bounded v3 receipt; mixed refs; no operational IDs` |

**Required extraction boundary:** 5 km route buffer around both candidate
hypotheses; 20 km hazard-context buffer, expanded only after hydrological
justification. These are audit extraction defaults from the blueprint, not
validity or safety thresholds.

**Administrative-unit hypothesis:** Kamrup Metropolitan, Nagaon, Hojai, Dima
Hasao, and Cachar. Current boundary intersection must be verified after graph
and administrative data import.

## 4. Restriction and route-feasibility checklist

| Check | Evidence required | Result |
|---|---|---|
| Current graph extract | Dated Geofabrik/OSM North-Eastern Zone PBF plus SHA-256 | **Established for bounded probe:** `north-eastern-zone-260909.osm.pbf`, OSM data as of `2026-09-09T20:21:20Z`, SHA-256 recorded in Path B evidence |
| Two candidate route results | GraphHopper output with graph version and edge IDs | **Routing sub-gate PASS (bounded):** 27 checksummed HTTP 200 receipts in GraphHopper 11.0 using all three exact profiles; no stable operational application edge IDs |
| Topology/continuity | Connected path from selected origin to selected destination | **All six audit-band endpoints represented** by independent legs and a threaded NH-27 query; NH-27 refs are mixed, NH-6 remains waypoint-biased, and endpoints are not surveyed facilities |
| Surface/road class/lanes | OSM tags reviewed per candidate | **Raw receipts plus corridor-edge mapping available**; no operational segment import |
| Bridges/tunnels/approaches | Typed segment mapping and structure constraints | Bridges/tunnels observed in path details; no typed operational segment import |
| `maxheight`/`maxweight`/`hgv` | Per-profile applicability for `light_goods`, `rigid_truck`, `emergency` | Exact profiles were run; `hgv` was missing and height/weight unset on returned paths |
| Access/direction/turns | Graph profile and restriction audit | v3 hard-excludes rigid-truck `hgv=DELIVERY`, `hgv=DESTINATION`, and `road_access=PRIVATE`; no such tags were encountered in this extract, and turn tables/complete direction legality remain unaudited |
| Construction/planned road handling | Current tag review; planned edges excluded | No `CONSTRUCTION` segment encountered in returned paths; planned-road authority review remains open |
| Authority cross-reference | NHAI/NHIDCL references mapped to bands | **Partial page evidence only** |
| Positive event/field review path | At least one usable, reviewable event path | **Not established** |

The v3 routing run narrows the routing uncertainty but is not a corridor
approval. Dated 2026-09-09 OSM plus GraphHopper 11 represents all six audit-band
endpoints for all three profiles with 27 checksummed receipts. The NH-27
candidate contains mixed road refs, band 5 has profile-dependent routing
preference divergence, and NH-6 remains waypoint-biased. No current
passability, legal, status, or recommendation claim follows. The corridor
remains provisional until operational graph/segment mapping, restriction and
authority review, and the remaining P0 evidence are accepted.

### 4a. Bounded real probe evidence (Path B commit `42c9205`, v3 current)

Path B v3 is the current authoritative real-evidence layer in
`data/corridor/graphhopper/real_evidence/v3/`. The v2 layer is superseded and
must not be cited as current. V3 corrects the rigid-truck conditional/private
access treatment and distinguishes the unconstrained direct query as a control
only; it does not alter the overall A-M0-01 P0 decision.

| Field | Recorded value |
|---|---|
| Extract | `https://download.geofabrik.de/asia/india/north-eastern-zone-260909.osm.pbf`; OSM data as of `2026-09-09T20:21:20Z` |
| Extract SHA-256 / retained path | `9250938dd6e8c61ad3ca533620a86c5d286e86f60c2bc45086e173f2ace068a9`; `D:\SIH-2026\NER_LENS_ARTIFACTS\m0\north-eastern-zone-260909.osm.pbf` outside git, reverified before/after v3 |
| Router | GraphHopper `11.0`, official release; one-time non-runtime scratch run |
| Profiles | Exact project-specific `light_goods` (3.5 t / 2.5 m), `rigid_truck` (16.0 t / 3.8 m), and `emergency` (7.5 t / 3.0 m) models |
| Receipts | **27 checksummed HTTP 200 `/route` receipts** plus raw `/info`: 3 direct-control, 3 threaded NH-27 via-bands, 18 independent NH-27 band legs, and 3 NH-6 waypoint-biased queries |
| Band coverage | All six audit-band endpoints represented for all three profiles; the six independent leg distances equal the threaded via-bands distance for each profile |
| Receipt hashes | `/info` `ddb9eb43a19ffd8e4faf02af217ff9f03b43db574e699f09171aa611f0872a6e`; response index `339ebe97b55cb21388d3d98b7f14dcde6fba08978cda46984e1e356030f3b7c5`; summary `4f4dc4bf0b50a8d41c19e66acacaabf205bc3d83701a9b681f5c925a358a0f26`; edge mapping `1370d2c15b3066063390d28d530b16c0661f45e3ed30c664260fa3ea1f331bec` |
| Query window | Local shell clock `2026-09-10T06:37:53Z` to `2026-09-10T06:37:57Z` |

The unconstrained `nh27_control_direct` query is **control-only**, not NH-27
corridor proof: it is dominated by NH6/NH37/SH38/SH-023 refs with NH27 only
about 2.1% of distance. The actual NH-27 candidate is the threaded query
through all six audited band endpoints, supported by six independent per-band
legs. Its measured NH27-ref share is 45.4% for `light_goods` and 60.6% for
`rigid_truck`/`emergency`, with other named and unnamed roads also present.
This is mixed-road evidence, not a single continuous NH27 way. On band 5
(Maibang–Harangajao/Balachera hill), `light_goods` takes a materially shorter
path than `rigid_truck`/`emergency`; the evidence attributes this to routing
preference (`distance_influence`), not a legality exclusion. NH-6 remains
waypoint-biased through Shillong and Jowai.

V3 hard-excludes `hgv=DELIVERY`, `hgv=DESTINATION`, and
`road_access=PRIVATE` for `rigid_truck`, and removes the unauthorized
`max_weight_except` bypass; the same max-weight correction is applied to all
three profiles. These tags were not encountered in the queried extract, so
the fix is conservative model correctness, not end-to-end exercise of those
conditions. `hgv` remained missing and `max_height`/`max_weight` unset on the
returned paths; no `CONSTRUCTION` segment or routing error was observed.

**Terra routing sub-gate conclusion:** the dated 2026-09-09 OSM plus
GraphHopper 11 evidence represents all six audit-band endpoints for all three
profiles, with mixed refs, hill-band preference divergence, and NH-6 waypoint
bias. It makes no current passability, legal, status, or recommendation
claim. Terra's routing sub-gate PASS is bounded evidence only and does not
authorize M1.

Limitations that remain explicit: this is one dated run against one extract;
turn-restriction tables are not exposed; OSM way IDs are not obtainable from
this GraphHopper API surface; no operational graph import or stable internal
segment IDs were established; and authority/reviewer, source terms, labels,
mission/consent, positive-event/ground-truth review, and policy-owner
thresholds remain missing. No route here is operationally verified.

## 5. Source and terms ledger

`Direct` means a public landing/download page was reachable. It does not imply
an API entitlement, redistribution right, freshness SLA, or operational
authority. `Replay` means only a small permitted/curated fixture may be used;
no raw private or unlicensed payload is committed here.

| ID | Source/use | Access classification | Verified observation on 2026-09-10 | Terms/permission state | Fallback and label |
|---|---|---|---|---|---|
| SRC-SIH | SIH-26002 requirement traceability | Direct official dynamic page | Page exposes PS 26002 and requirements for roads, routes, GPS, alerts, field reports, dashboards, multilingual/offline support | Local snapshot/diff is not preserved by this task; official traceability remains Sol's S-M0-01 dependency | Local dossier is `provisional research`, not an official snapshot |
| SRC-OSM | Base graph and restrictions | Direct; dated North-Eastern Zone extract used by Path B probe; ODbL | `north-eastern-zone-260909.osm.pbf`, OSM data as of 2026-09-09T20:21:20Z; SHA-256 recorded in section 4a | ODbL attribution/share-alike obligations apply; no private contributor metadata | Real probe only; stable operational graph import and segment mapping remain pending |
| SRC-GRAPHHOPPER | Bounded route probe | Official GraphHopper 11.0 release used by Path B outside runtime | V3 has 27 checksummed `/route` receipts using exact `light_goods`, `rigid_truck`, and `emergency` profiles, all six band endpoints, control/via-band/per-leg/NH-6 query roles, and corridor-edge mapping | Operational adapter terms, stable segment import, and policy approval remain unverified | Reproduce from Path B commit `42c9205`; v2 is superseded; no runtime claim |
| SRC-NHIDCL | Official corridor/project cross-reference | Direct official Assam page | Page lists `Daboka-Lahorijan` and `Balachera - Harangajao NH-27(New)`; page last updated 2026-09-09 | Page terms and redistribution of copied project documents not validated | Store URL/title/date metadata; use replay fixture for parser tests |
| SRC-NHAI | NH-27 section cross-reference | Inaccessible in this audit browser | URL is cited locally; PDF could not be fetched | Terms and content not independently checked | Use NHIDCL/Parliamentary sources only after independent retrieval; no copied PDF |
| SRC-IMD | Warnings/rainfall/nowcast context | Direct docs; API access may require IP allowlisting | API index and reference pages list district warnings, rainfall, nowcast, highway warnings; docs require attribution and mention IP allowlisting | API credentials/allowlisting and use terms not granted | `replay` permitted/curated response; source health `unavailable_until_approved` |
| SRC-GSI | Landslide inventory/susceptibility/event candidates | Portal/manual | Bhusanket page exposes field-validated inventory and susceptibility products | Machine/API access, download terms, field-validation metadata and redistribution not validated | Manual metadata plus replay fixture; never a closure source |
| SRC-CWC | River/flood context near crossings | Portal/manual; API not confirmed | Local blueprint identifies CWC portal and hydromet page; browser could not validate operational API | Access/cadence/terms unresolved | ASDMA/SACHET/replay fallback; source health `unavailable_until_approved` |
| SRC-ASDMA | Assam flood reports and partner path | Direct public pages | Flood report page and current contact page reachable; contact page lists CEO office and official email/phone | Report reuse/automation terms and partner permission not granted | Manual/curated replay; contact is outreach only |
| SRC-SACHET | Official CAP alert context | Direct public portal/RSS | Portal states geo-targeted, multi-lingual, near-real-time CAP dissemination and RSS | RSS/API terms and redistribution not separately approved | Curated CAP replay fixture; alerts are hazard evidence, never road status |
| SRC-AUTH | Operational road status | Partner-dependent | No named authority or current road-segment closure feed established | Written role/jurisdiction approval required | Demo-only seeded authority after Sol/human approval; otherwise status `unknown` |
| SRC-FIELD | Positive/negative ground truth | Partner-dependent | No interview, field protocol, or reviewer acceptance record | Partner, consent, safety and review required | Synthetic/replay reports visibly labelled; cannot validate ML |
| SRC-GPS | Mission progress/ETA | Partner/consent-dependent | No live device, carrier, or consent basis | Purpose, retention, device and mission consent required | Labelled GPS replay only |
| SRC-ULIP | Future logistics integration | Partner-dependent | Local docs describe onboarding/NDA/security review; no access | Written onboarding and use-case approval required | Lawful simulator/sample payload only |
| SRC-BHASHINI | Language service | Account/PoC/partner-dependent | Docs cited locally; no production permission or review | Human approval required for operational language | English + draft Assamese fixture marked `unreviewed` |

**Source-health rule:** unknown access, stale data, failed retrieval, or missing
terms must be shown as `unavailable|stale|failed|quarantined`; never as “no
hazard” or `open`.

## 6. Authority and reviewer route

The frozen contracts allow a scoped `district_officer` or explicitly configured
authority to publish `open|restricted|closed|unknown`, while a `reviewer`
reviews evidence. Those are system roles, not evidence that a real institution
has accepted the workflow.

| Needed role | Candidate outreach path | Current evidence | Blocking gap |
|---|---|---|---|
| Operational status authority | NHIDCL/NHAI corridor operations, Assam PWD/ASDMA, or district authority | Official pages/contact routes exist; no acceptance | Named person/role, jurisdiction, status publication and expiry authority |
| Evidence reviewer | ASDMA/DDMA, NHIDCL/NHAI, district official, or approved logistics operator | No interview or signed review protocol | Reviewer identity, scope, conflict resolution and response SLA |
| Mission owner | District health/medical-supply unit or established carrier | No partner identified | Mission route, vehicle, GPS consent and delivery window |
| Language reviewer | Native Assamese operational reviewer | No reviewer identified | Approval for safety-critical templates |

**No authority assertion is made.** ASDMA contact details are an outreach
route, not authorization. Until named authority and reviewer evidence exists,
status-changing and operational recommendation claims remain blocked.

## 7. Label feasibility and ground-truth plan

### Target and classes

Target: `verified operational disruption evidence affects segment s within six
hours of issue time t`. The intended classes are:

- `disrupted`: closed or materially restricted for the target vehicle within
  the horizon, supported by an authority notice, reviewed field report, or
  operational report tied to the segment;
- `not_disrupted_observed`: positively observed passable for the vehicle within
  the horizon;
- `unknown`: no reliable outcome observation;
- `ambiguous`: location, time, vehicle scope, or operational effect cannot be
  resolved.

Unreported segment-hours are not negatives. Hazard occurrence, publication,
retrieval, review, and operational effect must remain separate.

### Feasibility result

| Requirement | Current result |
|---|---|
| Positive-event source path | Candidate paths named: authority records, reviewed field reports, GSI/ASDMA/CWC/SACHET context; no usable event rows yet |
| Segment/time/vehicle mapping | Not established |
| Positive count and independent event groups | **Not measured** |
| Passability/negative path | No consented traversal or approved reviewer evidence |
| Reviewer and adjudication | Not assigned |
| Historical five-monsoon ledger | Not assembled |
| Label license/redistribution | Not checked per record |
| ML validation feasibility | **Not feasible yet; baseline/replay only** |

**Decision:** the label design is feasible, but label validation is not yet
feasible. A candidate model must not be trained or scored. A transparent
baseline may be demonstrated only with replay/synthetic data and must be
labelled as such; it is not field validation.

### Required positive-event path before M1

Obtain a named reviewer/authority and a permitted event ledger containing at
least one segment-linked event path, with observed/occurrence interval,
published/retrieved/reviewed times, vehicle scope, source snapshot/hash, terms,
and an adjudication outcome. Fewer than 30 independent positive event groups
later remains demonstration-only under the frozen specifications.

## 8. Prototype mission boundary

**Mission hypothesis:** one essential-medicine shipment from a Guwahati-area
warehouse to a Silchar-area receiving point, comparing NH-27 and the NH-6
direction for `light_goods`, `rigid_truck`, and `emergency` profiles.

Origin/destination facilities, cargo owner, vehicle owner, departure/deadline,
reviewer, GPS device and consent are **unassigned**. Any mission or GPS fixture
must be tagged `synthetic` or `replay`; it cannot be presented as a live trip,
partner validation, or measured ETA.

## 9. RouteVerificationPolicy inputs (unresolved where evidence is absent)

The API contract requires a versioned immutable policy. M0 records inputs and
owners; it must not invent global thresholds.

| Policy input | Audit value | State/owner |
|---|---|---|
| Policy ID/version | `UNASSIGNED` | Sol assigns after contract freeze |
| Graph scope/version | North-Eastern Zone OSM extract; exact checksum/version `UNASSIGNED` | Path B route audit + Sol freeze |
| Graph currency rule | `UNSET` | Operational owner must approve max age relative to extract cadence |
| Critical source classes | Status decisions, applicable legal/physical restrictions, and evidence supporting status; hazard feeds may affect risk | Sol + named authority; applicability still to be signed |
| Source-specific maximum ages | `UNSET` for IMD, GSI, CWC, ASDMA, SACHET, field evidence | Source cadence + named operational owner |
| Minimum evidence coverage | `UNSET` | Define segment×direction×vehicle coverage and approve threshold |
| Applicability | Required per segment, direction, vehicle profile, and departure window | Path A segment import + Path B route audit |
| Degraded recommendation | Conservative default: **false** until explicitly approved | Sol + operational owner |
| Hard-exclusion rule | Only active applicable status/physical/legal restrictions; never risk alone | Frozen contract; no live route tested |
| Extraction buffers | 5 km route; 20 km hazard context | Blueprint audit defaults, not policy thresholds |

Until the unresolved fields have an approving operational owner, every route
comparison must resolve conservatively to `insufficient_evidence` with
`recommended_route_id=null`. No numeric age/coverage value is asserted here.

## 10. Replay fixtures and provenance boundary

This task commits metadata-only manifests and a tiny fixture-case list. No raw
private, credentialed, or unlicensed source payload is included. Any future
fixture must carry source, retrieval time, SHA-256, terms/licence, parser
version, and one of `live_approved|replay|synthetic|partner_dependent`.

- `replay`: captured/curated payload is permitted for local tests but is not a
  live claim;
- `synthetic`: made for software behavior tests and cannot support accuracy;
- `partner_dependent`: blocked until written access/consent;
- `inaccessible`: cited but not independently retrieved.

## 11. P0 decision record

**Decision:** `P0 BLOCKED — do not start A-M1-01`
**Recommended corridor action:** keep the two hypotheses configurable while
the v3 bounded evidence is carried forward into the operational graph and
review process; change corridor through an ADR if either candidate fails.

Blocking evidence still required:

1. The v3 exact-profile bounded real probe, all six band endpoints, and 27 raw
   receipts are now recorded; stable segment IDs, an operational graph
   import/version, and reproducible operational restriction mapping are still
   required.
2. Restriction review covering topology, surface, bridge/tunnel, access,
   `maxheight`, `maxweight`, `hgv`, construction, turn, direction, and planned
   road exclusion, beyond the probe's path receipts and exposed path details.
3. A named status authority and evidence reviewer with jurisdiction and expiry
   decision rights.
4. Source access/terms approval for every live or downloaded source, plus
   permitted replay fallbacks where live access is unavailable.
5. A permitted positive-event and passability/ground-truth ledger path with
   reviewer adjudication; no fabricated metrics.
6. A named essential-medicine mission owner and GPS/field consent basis, or a
   signed replay-only mission boundary accepted by Sol/human owner.
7. Sol/operational-owner approval of graph currency, source-specific maximum
   ages, evidence coverage, applicability, and degraded recommendation rule.

### Exact dependency before A-M1-01

Sol must accept this ledger only after items 1–7 above are evidenced, Terra
P0 records a pass (or an explicit corridor change is completed), and the shared
M0 baseline/official snapshot dependency from S-M0-01 is green. Until then,
Path A may update evidence docs/manifests only; it must not add packages,
migrations, models, endpoints, or runtime integrations.

## 12 Source references

All pages below were retrieved or attempted on 2026-09-10 unless noted. The
local control documents were read from the branch at the start of this task.

- [Official SIH 2026 problem statements](https://www.sih.gov.in/sih2026PS) — PS 26002 page reachable; official snapshot still pending S-M0-01.
- [Geofabrik India downloads](https://download.geofabrik.de/asia/india.html) — North-Eastern Zone listing and ODbL notice reachable; dated extract evidence is recorded from Path B's bounded probe.
- [GraphHopper profiles](https://github.com/graphhopper/graphhopper/blob/master/docs/core/profiles.md) — Path B v3 used official 11.0 with exact project-specific `light_goods`, `rigid_truck`, and `emergency` models; routing sub-gate PASS is bounded and operational approval remains pending.
- [NHIDCL Assam corridors](https://www.nhidcl.com/en/assam/corridors) — related corridor project entries visible; no passability claim.
- [NHAI section annexure](https://nhai.gov.in/nhai/sites/default/files/tender/OtherDocuments/4_Annexure_1.pdf) — cited locally, inaccessible in the research browser.
- [IMD API hub](https://mausam.imd.gov.in/responsive/apis.php) and [API reference](https://api.imd.gov.in/public/api_reference.html) — docs reachable; allowlisting/terms remain.
- [ASDMA flood report](https://asdma.assam.gov.in/information-services/assam-flood-report) and [ASDMA contact](https://asdma.assam.gov.in/contacts/assam-state-disaster-management-authority-asdma) — pages reachable; partner approval absent.
- [NDMA SACHET](https://sachet.ndma.gov.in/) — CAP, geo-targeted, multilingual, RSS features visible; alert is not passability.
- [GSI Bhusanket](https://bhusanket.gsi.gov.in/) — field-validated inventory/susceptibility surfaces visible; machine access/terms unresolved.
- [OpenStreetMap copyright/licence](https://www.openstreetmap.org/copyright) — ODbL and attribution obligations.

## 13 Honest claims boundary

This audit can claim: the candidate hypotheses are grounded in the local
technical blueprint and official pages expose related infrastructure/source
surfaces. It cannot claim: both routes are routable, heavy-vehicle legality,
current road status, live API access, partner authority, field validation,
positive counts, ETA/model metrics, or production permissions.
