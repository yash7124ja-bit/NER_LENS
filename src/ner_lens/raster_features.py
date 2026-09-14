"""Local, provenance-checked segment raster summaries; no acquisition or model promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps require timezone")
    return result


def _checked_file(base: Path, entry: dict) -> Path:
    path = (base / entry["path"]).resolve()
    if sha256(path) != entry["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {path.name}")
    return path


def extract(manifest_path: Path, output: Path, cutoff: str) -> dict:
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import rasterio
    from pyproj import CRS, Transformer
    from rasterio.mask import mask
    from shapely.ops import transform

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issue_time = _time(cutoff)
    buffer_m = float(manifest.get("buffer_m", 100))
    if not math.isfinite(buffer_m) or not 0 < buffer_m <= 50000:
        raise ValueError("buffer_m must be finite, positive and at most 50000 metres")
    segment_path = _checked_file(manifest_path.parent, manifest["segments"])
    segments = gpd.read_file(segment_path)
    if segments.crs is None or CRS(segments.crs) != CRS.from_epsg(4326):
        raise ValueError("segment GeoJSON must declare or resolve to WGS84 EPSG:4326")
    if "segment_id" not in segments or segments.empty:
        raise ValueError("nonempty segment_id column required")
    if segments.segment_id.isna().any() or segments.segment_id.duplicated().any():
        raise ValueError("segment IDs must be unique and present")
    if any(not str(value).strip() for value in segments.segment_id):
        raise ValueError("segment IDs cannot be blank")
    buffers = []
    for geometry in segments.geometry:
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            raise ValueError("empty or invalid segment geometry")
        if geometry.geom_type not in {"LineString", "MultiLineString"}:
            raise ValueError("segments must be LineString or MultiLineString")
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -85 <= south <= north <= 85):
            raise ValueError("segment coordinates outside supported longitude/latitude bounds")
        if east - west > 10 or north - south > 10:
            raise ValueError("segment extent too large for local metric buffering; split first")
        center = geometry.centroid
        local = CRS.from_proj4(
            f"+proj=aeqd +lat_0={center.y} +lon_0={center.x} +datum=WGS84 +units=m"
        )
        forward = Transformer.from_crs(4326, local, always_xy=True).transform
        backward = Transformer.from_crs(local, 4326, always_xy=True).transform
        buffers.append(transform(backward, transform(forward, geometry).buffer(buffer_m)))
    rasters = manifest.get("rasters", [])
    if not rasters:
        raise ValueError("at least one raster source required")
    output_rows = []
    variables = set()
    for entry in rasters:
        variable = entry["variable"]
        if not isinstance(variable, str) or not variable.strip() or variable in variables:
            raise ValueError("raster variables must be nonempty and unique")
        variables.add(variable)
        for field in ("units", "source", "license", "window"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"explicit {field} required")
        observed, published, retrieved = (
            _time(entry[key]) for key in ("observed_at", "published_at", "retrieved_at")
        )
        if not observed <= published <= retrieved <= issue_time:
            raise ValueError("future feature or invalid source timestamp chronology")
        raster_path = _checked_file(manifest_path.parent, entry)
        with rasterio.open(raster_path) as source:
            if source.crs is None:
                raise ValueError("raster CRS required")
            band = entry.get("band", 1)
            if not isinstance(band, int) or isinstance(band, bool) or not 1 <= band <= source.count:
                raise ValueError("invalid raster band")
            if (
                not all(math.isfinite(v) for v in source.transform)
                or source.transform.determinant == 0
            ):
                raise ValueError("invalid raster geotransform")
            project = Transformer.from_crs(4326, source.crs, always_xy=True).transform
            for segment_id, buffer in zip(segments.segment_id, buffers, strict=True):
                polygon = transform(project, buffer)
                if not all(math.isfinite(v) for v in polygon.bounds):
                    raise ValueError("raster projection produced invalid coordinates")
                reason = None
                try:
                    data, _ = mask(
                        source, [polygon], crop=True, filled=False, all_touched=True, indexes=band
                    )
                    values = data.compressed().astype(float)
                    values = values * source.scales[band - 1] + source.offsets[band - 1]
                    values = values[np.isfinite(values)]
                    if not len(values):
                        reason = "nodata"
                except ValueError as error:
                    if "do not overlap" not in str(error):
                        raise
                    values = np.array([], dtype=float)
                    reason = "outside_raster"
                output_rows.append(
                    {
                        "segment_id": str(segment_id),
                        "variable": variable,
                        "units": entry["units"],
                        "window": entry["window"],
                        "source": entry["source"],
                        "license": entry["license"],
                        "observed_at": observed,
                        "published_at": published,
                        "retrieved_at": retrieved,
                        "issued_at": issue_time,
                        "age_hours": (issue_time - observed).total_seconds() / 3600,
                        "mean": float(values.mean()) if len(values) else None,
                        "minimum": float(values.min()) if len(values) else None,
                        "maximum": float(values.max()) if len(values) else None,
                        "pixel_count": len(values),
                        "missing": not bool(len(values)),
                        "missing_reason": reason,
                        "buffer_m": buffer_m,
                        "raster_sha256": entry["sha256"],
                        "segments_sha256": manifest["segments"]["sha256"],
                        "manifest_sha256": sha256(manifest_path),
                        "raster_crs": str(source.crs),
                        "schema_version": "segment-raster-summary-v1",
                    }
                )
    provenance = {
        "schema_version": "segment-raster-summary-v1",
        "manifest_sha256": sha256(manifest_path),
        "segments_sha256": manifest["segments"]["sha256"],
        "issued_at": issue_time.isoformat(),
        "rows": len(output_rows),
        "sampling": "all-touched pixels in local AEQD metre buffer",
        "approved_for_operations": False,
    }
    table = pa.Table.from_pandas(pd.DataFrame(output_rows), preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"ner_lens_provenance"] = json.dumps(provenance, sort_keys=True).encode()
    # Write only after all inputs have passed validation and extraction.
    pq.write_table(table.replace_schema_metadata(metadata), output)
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = extract(args.manifest, args.output, args.cutoff)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Raster extraction blocked: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

