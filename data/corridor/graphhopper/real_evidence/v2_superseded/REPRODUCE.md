# Reproducing the B-M0-01 second corrective-audit real evidence run

Executed 2026-09-10 in a scratch sandbox outside the repository and outside
any Path A/B/Sol worktree (`D:/SIH-2026/.m0-graph-sandbox2/`, deleted after
evidence extraction). The dated PBF is retained separately (not deleted) at
`D:\SIH-2026\NER_LENS_ARTIFACTS\m0\north-eastern-zone-260909.osm.pbf`.

## Boundary statement (read first)

This is real, one-time evidence gathering, not a running service and not
the backend routing adapter. Nothing here is a runtime GraphHopper
deployment for NER LENS; B-M1-02 is where the backend adapter is actually
built. The tests added in this audit (`tests/path_b/routing/
test_real_evidence_receipts.py`) validate the **committed receipt files**
in this directory, not a live service — there is no server running when
those tests execute.

## 1. Retrieve the dated extract (retain outside git)

```bash
mkdir -p "D:\SIH-2026\NER_LENS_ARTIFACTS\m0"
cd "D:\SIH-2026\NER_LENS_ARTIFACTS\m0"
date -u +"%Y-%m-%dT%H:%M:%SZ"   # capture before-timestamp yourself; do not trust HTTP Date
curl -sS -m 300 -D headers_download.txt -o north-eastern-zone-260909.osm.pbf \
  https://download.geofabrik.de/asia/india/north-eastern-zone-260909.osm.pbf
date -u +"%Y-%m-%dT%H:%M:%SZ"   # capture after-timestamp yourself
# byte size 109305518, md5 eee3d24fe21d7be1d1b4f01603979273 (verify against
# https://download.geofabrik.de/asia/india/north-eastern-zone-latest.osm.pbf.md5)
```

## 2. Official GraphHopper 11.0 jar (not a third-party image)

```bash
curl -sS -L -o graphhopper-web-11.0.jar \
  https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar
```

## 3. Project-specific custom models

`light_goods.json`, `rigid_truck.json`, and `emergency.json` in this
directory are the exact files used — authored to match
`data/corridor/graphhopper/vehicle_profiles.yaml`'s numeric limits
(3.5t/2.5m, 16.0t/3.8m, 7.5t/3.0m respectively). `rigid_truck.json` is
adapted from GraphHopper's official `truck.json` example with this
project's own thresholds substituted; `light_goods.json`/`emergency.json`
are project-authored. `graphhopper-config.yml` in this directory is the
exact config used.

## 4. Run GraphHopper

```bash
docker run -d --name gh-audit2 -p 8989:8989 \
  -v "<sandbox_dir>:/data" -w /data \
  eclipse-temurin:21-jre-jammy \
  java -Xmx3g -jar /data/graphhopper-web-11.0.jar server /data/graphhopper-config.yml
```

`rigid_truck` uses `turn_costs` (edge-based CH), which takes noticeably
longer to prepare (~80s for this extract) than the node-based `light_goods`/
`emergency` profiles.

## 5. Query /info and both routes for all three profiles

```bash
curl -sS http://localhost:8989/info   # -> raw_info.json in this directory

# NH-27 primary (direct, no via-points)
curl -G http://localhost:8989/route \
  --data-urlencode "point=26.1445,91.7362" --data-urlencode "point=24.8333,92.7789" \
  --data-urlencode "profile=light_goods" --data-urlencode "points_encoded=false" \
  --data-urlencode "instructions=true" \
  --data-urlencode "details=road_environment" --data-urlencode "details=road_access" \
  --data-urlencode "details=road_class" --data-urlencode "details=max_height" \
  --data-urlencode "details=max_weight" --data-urlencode "details=hgv"
# repeat with profile=rigid_truck and profile=emergency

# NH-6 alternative (waypoint-biased via Shillong, Jowai)
curl -G http://localhost:8989/route \
  --data-urlencode "point=26.1445,91.7362" --data-urlencode "point=25.5788,91.8933" \
  --data-urlencode "point=25.4340,92.1935" --data-urlencode "point=24.8333,92.7789" \
  --data-urlencode "profile=light_goods" ... (same flags as above)
# repeat with profile=rigid_truck and profile=emergency
```

Six raw responses are saved verbatim in `raw_responses/`. `response_index.json`
maps each to its request parameters and SHA-256. `result_summary.json`
aggregates distance/time/street-names/path-details per query, and is itself
hashed in `real_extract_provenance.yaml` (`result_summary_sha256`).

## 6. Verify the retained PBF hash again after the route run

```bash
cd "D:\SIH-2026\NER_LENS_ARTIFACTS\m0"
python -c "import hashlib; d=open('north-eastern-zone-260909.osm.pbf','rb').read(); print(hashlib.sha256(d).hexdigest())"
# must equal the pre-run sha256 recorded in real_extract_provenance.yaml
```

## 7. Clean up

```bash
docker stop gh-audit2 && docker rm gh-audit2
rm -rf D:/SIH-2026/.m0-graph-sandbox2   # jar, PBF copy, generated graph-cache — never committed
# the retained PBF at D:\SIH-2026\NER_LENS_ARTIFACTS\m0\ is NOT deleted
```
