# v1 real evidence — superseded

This directory's contents are the first real GraphHopper evidence run
(2026-09-10, first B-M0-01 corrective audit). Terra's second review found
two defects in it, both corrected in `../v2/`:

1. **Timestamp inconsistency.** `real_extract_provenance.yaml` recorded an
   HTTP response `Date` header (`04:36:50Z`) as if it were the retrieval
   time, alongside a separately-worded local completion note ("by
   2026-09-10T04:08 local") that could not be reconciled under any UTC/IST
   interpretation. Root cause: Geofabrik serves the file through a caching
   proxy, and the `Date` header on a cache hit reflects when the cached
   response was generated, not when this session retrieved it. `v2/`
   replaces this with the session's own independently captured shell-clock
   timestamps (before/after every network call) and explains the
   methodology.
2. **Generic profiles only.** This run queried GraphHopper's official
   example `car`/`truck` custom models as proxies for `light_goods`/
   `emergency`/`rigid_truck`, not project-specific models matching
   `data/corridor/graphhopper/vehicle_profiles.yaml`'s exact numeric
   limits. `v2/` uses three project-authored custom models
   (`light_goods.json`, `rigid_truck.json`, `emergency.json`) with the
   exact 3.5t/2.5m, 16.0t/3.8m, and 7.5t/3.0m thresholds respectively, and
   no invented emergency legal exemption.

These files are retained for traceability, not deleted, per the project's
"preserve provenance, never silently overwrite" rule. `v2/` is the current,
authoritative real-evidence layer. Do not treat this directory as current
evidence.
