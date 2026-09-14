# Local geospatial feature extraction

Install `uv sync --extra geospatial --extra evaluation`, then supply licensed local data:

```
uv run python -m ner_lens.raster_features data/manifest.json --cutoff 2026-06-01T12:00:00Z --output data/features-v1.parquet
```

The GeoJSON must contain nonempty, valid WGS84 LineString/MultiLineString features with unique `segment_id` properties. This command never downloads a raster. It verifies SHA-256 for both segments and every raster before producing a Parquet artifact. Example manifest (replace placeholders with actual hashes and source metadata):

```json
{
  "buffer_m": 100,
  "segments": {"path": "segments.geojson", "sha256": "ACTUAL_SHA256"},
  "rasters": [{
    "path": "rainfall-24h.tif",
    "sha256": "ACTUAL_SHA256",
    "variable": "rainfall_24h",
    "units": "mm",
    "window": "preceding 24 hours",
    "source": "provider and product version",
    "license": "terms reference",
    "band": 1,
    "observed_at": "2026-06-01T09:00:00Z",
    "published_at": "2026-06-01T10:00:00Z",
    "retrieved_at": "2026-06-01T11:00:00Z"
  }]
}
```

Relative paths resolve beside the manifest. All timestamps require timezones and must satisfy observation <= publication <= retrieval <= cutoff. Units and accumulation window must explicitly describe the selected band's values **after** the raster's scale/offset. No inferred unit conversion occurs. The operator must validate those declarations against the original product. Static DEM rasters likewise require honest product availability dates; old terrain age does not make a future publication available retrospectively.

GeoPandas loads and validates segments; PyProj and Shapely create a local azimuthal equidistant projection per segment, buffer in metres, then transform the polygon into each raster CRS. Rasterio/GDAL reads all touched pixels in the buffer. Output contains mean, minimum, maximum, valid pixel count, missing flag/reason, source age, timestamps, units, window, CRS and all provenance hashes. Nodata, masked and nonfinite values are excluded. An entirely missing buffer returns null statistics, never zero; nonoverlap is distinguished from nodata. Raster scale/offset is applied to valid pixels. Explicit raster CRS and invertible finite transform are required.

Pandas/PyArrow writes one row per segment/variable with `segment-raster-summary-v1`. Parquet schema metadata also contains `ner_lens_provenance` JSON including cutoff, sampling policy and manifest hash. Output remains `approved_for_operations: false`. All validation and extraction completes before output writing begins; choose a new versioned output filename for each run.

The supported scope is corridor segments spanning at most 10 degrees, latitudes within 85 degrees, and buffers up to 50 km. Split larger or dateline-spanning features before running. All-touched statistics are unweighted pixel summaries, not area-weighted hydrological analysis; coarse cells do not establish local road safety. Missing coverage is recorded but partial coverage is not a guarantee of representativeness. This tool summarizes supplied slope/DEM/rainfall products; it does not derive slope, process Sentinel radar, establish licensing, or validate sources scientifically. No real raster or evaluation measurements are bundled. Joining these feature rows to independently verified outcome labels remains a deliberate curated step.

```
uv run pytest tests/test_raster_features.py -q
```

Tests use clearly synthetic mini GeoTIFFs, verify known values in geographic and projected CRSs, nodata preservation, provenance, hash and temporal failures, and fail-closed CLI behavior.
