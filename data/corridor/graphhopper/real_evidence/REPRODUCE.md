# Reproducing the B-M0-01 real GraphHopper evidence run

Executed 2026-09-10 in a scratch sandbox outside the repository
(`D:/SIH-2026/.m0-graph-sandbox/`), not inside any Path B/A/Sol worktree.
No files from that sandbox are committed except this directory's contents
(config, official custom models, and derived result summaries).

## 1. Download the dated extract

```bash
curl -sS -m 300 -o north-eastern-zone-260909.osm.pbf \
  https://download.geofabrik.de/asia/india/north-eastern-zone-260909.osm.pbf
# byte size 109305518, md5 eee3d24fe21d7be1d1b4f01603979273 (matches Geofabrik's .md5 file)
```

## 2. Download the official GraphHopper 11.0 release jar and example custom models

```bash
curl -sS -L -o graphhopper-web-11.0.jar \
  https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar
curl -sS -L -o my_car.json \
  https://raw.githubusercontent.com/graphhopper/graphhopper/11.0/core/src/main/resources/com/graphhopper/custom_models/car.json
curl -sS -L -o my_truck.json \
  https://raw.githubusercontent.com/graphhopper/graphhopper/11.0/core/src/main/resources/com/graphhopper/custom_models/truck.json
```

## 3. Run GraphHopper (official Eclipse Temurin JRE image, not a third-party GraphHopper image)

```bash
docker run -d --name gh-audit -p 8989:8989 \
  -v "<sandbox_dir>:/data" -w /data \
  eclipse-temurin:21-jre-jammy \
  java -Xmx3g -jar /data/graphhopper-web-11.0.jar server /data/config.yml
```

`config.yml` in this directory is the exact file used (profiles `car`, `truck`;
`graph.encoded_values` includes `hgv, max_width, max_height, max_weight,
max_weight_except, road_access`).

## 4. Query both candidates for both profiles

```bash
# NH-27 primary (direct)
curl -G http://localhost:8989/route \
  --data-urlencode "point=26.1445,91.7362" --data-urlencode "point=24.8333,92.7789" \
  --data-urlencode "profile=car" --data-urlencode "points_encoded=false" \
  --data-urlencode "instructions=false" \
  --data-urlencode "details=road_environment" --data-urlencode "details=road_access" \
  --data-urlencode "details=road_class" --data-urlencode "details=max_height" \
  --data-urlencode "details=max_weight" --data-urlencode "details=hgv"

# repeat with profile=truck and ch.disable=true (truck is LM-prepared, not CH-prepared)
# repeat both with extra via-points 25.5788,91.8933 (Shillong) and 25.4340,92.1935 (Jowai)
# to bias the route onto the NH-6 hypothesis for the nh6_* queries.
```

Full parameter sets for all four queries are recorded in
`real_extract_provenance.yaml` under `queries_run`.

## 5. Result

All four queries returned HTTP 200. See `real_route_results_summary.json`
for distance/time and aggregated `path_details` value counts (bridge/tunnel/
ford presence, road class mix, and the real absence of `hgv`/`max_height`/
`max_weight` OSM tags along the returned paths).
