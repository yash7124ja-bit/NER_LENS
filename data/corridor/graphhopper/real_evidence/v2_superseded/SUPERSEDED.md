# v2 is superseded by v3

This directory (`real_evidence/v2_superseded/`, formerly `real_evidence/v2/`)
is preserved for provenance but is **not authoritative**. Terra's routing
verdict on the second corrective audit found it BLOCKED on two grounds that
`real_evidence/v3/` corrects:

1. **`rigid_truck.json` converted three hard-exclusion conditions into a
   small speed penalty instead of an exclusion.** The priority rule
   `{ "if": "road_access == PRIVATE || hgv == DELIVERY || hgv == DESTINATION",
   "multiply_by": "0.1" }` only made those ways 10x less attractive; it did
   not prevent the router from using one if nothing shorter existed. v3's
   `rigid_truck.json` hard-excludes (`multiply_by: "0"`) `hgv == DELIVERY`,
   `hgv == DESTINATION`, and `road_access == PRIVATE`, matching the existing
   hard-exclusion treatment already given to `hgv == NO`.

2. **`max_weight_except` could silently bypass an active max_weight
   restriction below the profile's limit**, with no authorization input in
   M0 to justify that bypass. v3 removes the `max_weight_except == MISSING`
   carve-out from `rigid_truck.json` (and, as a consistency extension, from
   `light_goods.json` and `emergency.json` too) so any `max_weight` below a
   profile's own limit excludes the segment unconditionally.

3. **The only "NH-27 candidate" evidence in v2 was a direct, unconstrained
   two-point query** (`nh27_light_goods.json` etc., origin -> destination,
   no via-points). That query's own `street_ref` path detail (not
   inspected closely enough in v2's summary) shows it is dominated by
   `NH6`/`NH37`/`SH38, SH-023` refs with only a small `NH27` fraction --
   i.e. it is GraphHopper's own shortest/fastest path, not a trace of the
   audited NH-27 corridor, and v2 did not make this distinction explicit or
   provide a band-level corridor-edge mapping. v3 adds an explicit
   via-band-waypoint NH-27 query (through the six audited bands' own
   endpoints) plus six independent per-band leg queries, and retains the
   original direct query only as a labelled `nh27_control_direct` control,
   never as NH-27 continuity evidence.

v2's `raw_extract_provenance.yaml` timestamp-methodology correction (fixing
the first corrective audit's HTTP-Date-vs-local-clock inconsistency) remains
valid and unchanged in method; v3 reuses the same methodology.

See `data/corridor/graphhopper/real_evidence/v3/` for the current evidence
and `docs/decisions/route-audit.md` section 4a for the full writeup.
