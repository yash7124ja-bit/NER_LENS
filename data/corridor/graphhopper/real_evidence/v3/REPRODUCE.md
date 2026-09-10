# Reproducing the B-M0-01 third routing-evidence correction (v3)

Executed 2026-09-10 in a scratch sandbox outside the repository
(`D:/SIH-2026/.m0-graph-sandbox3/`, deleted after evidence extraction). The
dated PBF is reused, unchanged, from
`D:\SIH-2026\NER_LENS_ARTIFACTS\m0\north-eastern-zone-260909.osm.pbf`
(retained by the v2 run; re-verified byte-identical here, not
re-downloaded).

## Boundary statement (read first)

This is real, one-time evidence gathering, not a running service and not
the backend routing adapter. `tests/path_b/routing/
test_real_evidence_receipts.py` validates the **committed receipt files**
in `data/corridor/graphhopper/real_evidence/v3/`, not a live service --
there is no server running when those tests execute.

## 1. Reuse the retained extract (do not re-download)

```bash
python -c "import hashlib; d=open('north-eastern-zone-260909.osm.pbf','rb').read(); print(hashlib.sha256(d).hexdigest())"
# must equal 9250938dd6e8c61ad3ca533620a86c5d286e86f60c2bc45086e173f2ace068a9
```

## 2. Official GraphHopper 11.0 jar (re-downloaded fresh, same official artifact)

```bash
curl -sS -L -o graphhopper-web-11.0.jar \
  https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar
# sha256 b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def, identical to v1/v2
```

## 3. Corrected custom models and config

`light_goods.json`, `rigid_truck.json`, `emergency.json`, and
`graphhopper-config.yml` in this directory are the exact files used.
`rigid_truck.json` is the M0 safety-corrected version (see
`real_extract_provenance.yaml` vehicle_profiles.rigid_truck.change_from_v2);
`light_goods.json`/`emergency.json` carry the same max_weight_except
consistency fix.

## 4. Run GraphHopper (Windows/git-bash note)

```bash
MSYS_NO_PATHCONV=1 docker run -d --name gh-audit3 -p 8989:8989 \
  -v "<sandbox_dir>:/data" -w /data \
  eclipse-temurin:21-jre-jammy \
  java -Xmx3g -jar /data/graphhopper-web-11.0.jar server /data/graphhopper-config.yml
```

Without `MSYS_NO_PATHCONV=1`, git-bash mangles the `-w /data` argument into
a Windows path and Docker rejects it.

## 5. Query /info and 27 route combinations

```bash
curl -sS http://localhost:8989/info   # -> raw_info.json

# per profile in {light_goods, rigid_truck, emergency}:
#   nh27_control_direct        : point=<Guwahati> point=<Silchar>                          (control only)
#   nh27_via_bands              : point=<Guwahati> point=<Nagaon> point=<Doboka>
#                                  point=<Lanka/Lumding> point=<Maibang>
#                                  point=<Harangajao/Balachera> point=<Silchar>              (the NH-27 candidate)
#   nh27_leg1..leg6_<band>      : the 6 consecutive pairs of the above, queried independently
#   nh6_alternative             : point=<Guwahati> point=<Shillong> point=<Jowai> point=<Silchar>
# details=road_environment,road_access,road_class,max_height,max_weight,hgv,street_ref
# points_encoded=false, instructions=true
```

See `run_queries.sh` logic reproduced above; the exact waypoint coordinates
are recorded in `real_extract_provenance.yaml routes_queried`. All 27 raw
responses are saved verbatim in `raw_responses/`; `response_index.json`
maps each to its SHA-256. `result_summary.json` aggregates
distance/time/street-ref-by-distance/street-names/path-details per query.
`corridor_edge_mapping.json` derives the per-band road-ref mapping and the
band-5 divergence finding from `result_summary.json`.

## 6. Verify the retained PBF hash again after the route run

```bash
python -c "import hashlib; d=open('north-eastern-zone-260909.osm.pbf','rb').read(); print(hashlib.sha256(d).hexdigest())"
# must still equal 9250938dd6e8c61ad3ca533620a86c5d286e86f60c2bc45086e173f2ace068a9
```

## 7. Clean up

```bash
docker stop gh-audit3 && docker rm gh-audit3
rm -rf D:/SIH-2026/.m0-graph-sandbox3   # jar, PBF copy, generated graph-cache -- never committed
# the retained PBF at D:\SIH-2026\NER_LENS_ARTIFACTS\m0\ is NOT deleted
```
