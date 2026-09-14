import json

import pytest

pytest.importorskip("rasterio")
pytest.importorskip("geopandas")
pytest.importorskip("pyarrow")
import numpy as np
import pyarrow.parquet as pq
import rasterio
from rasterio.transform import from_origin

from ner_lens.raster_features import extract, main, sha256


def fixture(tmp_path, *, crs="EPSG:4326", nodata=False):
    segment = tmp_path / "segments.geojson"
    segment.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"segment_id": "TEST_ONLY"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-0.0051, 0.005], [-0.0049, 0.005]],
                        },
                    }
                ],
            }
        )
    )
    raster = tmp_path / "TEST_ONLY.tif"
    transform = (
        from_origin(-0.01, 0.01, 0.01, 0.01)
        if crs == "EPSG:4326"
        else from_origin(-1000, 1000, 1000, 1000)
    )
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999,
    ) as file:
        file.write(np.full((2, 2), -9999 if nodata else 7, dtype="float32"), 1)
    manifest = tmp_path / "manifest.json"
    data = {
        "segments": {"path": segment.name, "sha256": sha256(segment)},
        "buffer_m": 10,
        "rasters": [
            {
                "path": raster.name,
                "sha256": sha256(raster),
                "variable": "rain_24h",
                "units": "mm",
                "source": "TEST_ONLY",
                "license": "synthetic fixture",
                "window": "24 hours",
                "observed_at": "2024-06-01T00:00:00Z",
                "published_at": "2024-06-01T00:01:00Z",
                "retrieved_at": "2024-06-01T00:02:00Z",
            }
        ],
    }
    manifest.write_text(json.dumps(data))
    return manifest, data


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:3857"])
def test_known_values_metric_buffer_and_parquet_provenance(tmp_path, crs):
    manifest, _ = fixture(tmp_path, crs=crs)
    output = tmp_path / "features.parquet"
    result = extract(manifest, output, "2024-06-01T01:00:00Z")
    table = pq.read_table(output)
    row = table.to_pylist()[0]
    assert row["mean"] == row["minimum"] == row["maximum"] == 7
    assert row["pixel_count"] == 1
    assert row["missing"] is False
    assert row["age_hours"] == 1
    assert row["manifest_sha256"] == sha256(manifest)
    assert json.loads(table.schema.metadata[b"ner_lens_provenance"]) == result
    assert result["approved_for_operations"] is False


def test_nodata_is_missing_not_zero(tmp_path):
    manifest, _ = fixture(tmp_path, nodata=True)
    output = tmp_path / "features.parquet"
    extract(manifest, output, "2024-06-01T01:00:00Z")
    row = pq.read_table(output).to_pylist()[0]
    assert row["missing"] is True
    assert row["mean"] is None
    assert row["pixel_count"] == 0
    assert row["missing_reason"] == "nodata"


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda d: d["rasters"][0].update(sha256="incorrect"), "SHA-256"),
        (lambda d: d["rasters"][0].update(retrieved_at="2025-01-01T00:00:00Z"), "future"),
        (lambda d: d["rasters"][0].update(units=""), "units"),
        (lambda d: d.update(buffer_m=-1), "buffer_m"),
    ],
)
def test_invalid_manifest_fails_before_output(tmp_path, mutation, match):
    manifest, data = fixture(tmp_path)
    mutation(data)
    manifest.write_text(json.dumps(data))
    output = tmp_path / "features.parquet"
    with pytest.raises(ValueError, match=match):
        extract(manifest, output, "2024-06-01T01:00:00Z")
    assert not output.exists()


def test_cli_rejects_missing_input(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(tmp_path / "absent.json"),
                "--cutoff",
                "2024-01-01T00:00:00Z",
                "--output",
                str(tmp_path / "out.parquet"),
            ]
        )
    assert error.value.code == 2
