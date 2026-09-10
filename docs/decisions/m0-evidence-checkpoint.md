# M0 evidence integration checkpoint

**Recorded:** 2026-09-10  
**Overall Terra P0:** `BLOCKED`  
**Routing sub-gate:** `PASS`  
**Runtime authorization:** none; M1 must not start

## Integrated evidence

- Sol official snapshot: `d21b2a7`
- Path A corridor/source/label audit through: `92c4136`
- Path B route/GraphHopper audit through: `42c9205`
- Main integration commits: `79ce784`, `7d3456f`
- Independent checks: Path A `5 passed`; Path B `79 passed`; retained PBF size and SHA-256/MD5 match the committed provenance.

## Corridor conclusion

On the dated 2026-09-09 OSM extract, GraphHopper 11 returned HTTP 200 paths through all six specified NH-27 audit-band endpoints for the three project vehicle profiles. This establishes graph representability of the audited corridor hypothesis, not a single continuously tagged NH-27 road: the measured paths include NH27 and other road references, with one profile-preference divergence in the hill band. The unconstrained Guwahati–Silchar route is a control and must not be cited as NH-27 evidence. The NH-6 alternative is waypoint-biased through Shillong and Jowai. Neither result establishes current passability, legal or structural clearance, operational status, or a route recommendation.

## Non-routing P0 blockers

The following require human or operational/data-partner evidence and cannot be replaced by engineering inference:

1. Named operational status authority, jurisdiction, publication/expiry rights, and conflict procedure.
2. Named evidence reviewer and adjudication procedure.
3. Named essential-medicine mission owner plus GPS/field-report consent and retention basis.
4. Approved access, storage, redistribution and cadence terms for the selected IMD, GSI, CWC, ASDMA and SACHET inputs.
5. A permitted segment/time/vehicle ground-truth ledger with reviewer-adjudicated positive events and passability evidence.
6. Operational-owner approval of `RouteVerificationPolicy` graph currency, source maximum ages, minimum evidence coverage, applicability and degraded-recommendation rules.

Until these are resolved, route mode defaults to `insufficient_evidence`, `recommended_route_id` is null, supervised ML is not justified, and all source/mission/GPS demonstrations remain explicitly replay-only.

## Non-blocking routing limitations

- The queried real paths did not exercise `DELIVERY`, `DESTINATION`, `PRIVATE`, or below-limit weight tags; structural regression tests cover the conservative exclusion rules.
- NH-27 is a measured mixed-road corridor, not continuous NH-27-tagged geometry.
- NH-6 remains waypoint-biased.
- Turn-restriction extraction and OSM way IDs were unavailable through the used GraphHopper API.
- This is one dated graph run, not continuous monitoring or an operational segment import.

## Decision

Accept the A/B M0 artifacts as a bounded evidence checkpoint. Do not record M0 or Terra P0 as complete, and do not authorize `A-M1-01`, `B-M1-01`, `B-M1-02`, or any other runtime task.
