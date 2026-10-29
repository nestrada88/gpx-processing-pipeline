"""NV-05 end-to-end numerical consistency across F02/F03/F04/F06/F09."""

from hashlib import sha256
from math import isclose
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline.pipeline import run_pipeline
from gpx_pipeline.pipeline_config import PipelineConfig


GPX_NS = "http://www.topografix.com/GPX/1/1"
EQUATORIAL_DEGREE_M = 111_319.49079327357


def _source(tmp_path):
    """Two disconnected, independently timed segments; no implied joining edge."""
    path = tmp_path / "source.gpx"
    path.write_text(
        f'<gpx xmlns="{GPX_NS}" version="1.1" creator="nv05">'
        '<trk><trkseg>'
        '<trkpt lat="0" lon="0"><time>2026-01-01T00:00:00Z</time></trkpt>'
        '<trkpt lat="0" lon="0.001"><time>2026-01-01T00:01:00Z</time></trkpt>'
        '</trkseg><trkseg>'
        '<trkpt lat="0.01" lon="0.01"><time>2026-01-01T01:00:00Z</time></trkpt>'
        '<trkpt lat="0.01" lon="0.011"><time>2026-01-01T01:02:00Z</time></trkpt>'
        '</trkseg></trk></gpx>',
        encoding="utf-8",
    )
    return path


def _dem(tmp_path):
    """Constant-elevation DEM covering both independent segments."""
    path = tmp_path / "flat.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=32, height=32,
        count=1, dtype="float32", crs="EPSG:4326",
        transform=from_origin(-.005, .02, .001, .001),
        nodata=-9999,
    ) as raster:
        raster.write(np.full((32, 32), 100.0, dtype=np.float32), 1)
        raster.set_band_unit(1, "m")
    return path


def _read(output, name):
    """Read one serialized pipeline product as JSON."""
    return json.loads((output / name).read_bytes())


def test_process_analyze_consistency_with_complete_synthetic_dem(tmp_path):
    """Common artifacts agree exactly; route and forecast statistics reconcile."""
    source = _source(tmp_path)
    dem = _dem(tmp_path)
    before = source.read_bytes()
    outputs = (tmp_path / "analysis", tmp_path / "process")
    for command, destination in zip(("analyze", "process"), outputs):
        run_pipeline(PipelineConfig(
            command=command, input_path=source, output_dir=destination,
            dem_path=dem, adaptive_sampling=True, forecast=True,
        ))
    for name in (
        "analytical/dataset.json",
        "analytical/route-analysis.json",
        "analytical/terrain-sampling.json",
        "analytical/activity-forecast.json",
    ):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    dataset = _read(outputs[0], "analytical/dataset.json")
    report = _read(outputs[0], "analytical/route-analysis.json")
    sampling = _read(outputs[0], "analytical/terrain-sampling.json")
    forecast = _read(outputs[0], "analytical/activity-forecast.json")
    source_hash = sha256(before).hexdigest()
    assert all(
        result["source_sha256"] == source_hash
        for result in (dataset, report, forecast)
    )
    assert sampling["sampling"]["source_sha256"] == source_hash
    assert len(dataset["segments"]) == len(report["segments"]) == 2
    assert len(sampling["sampling"]["segments"]) == 2
    expected_segment_distance = EQUATORIAL_DEGREE_M / 1000
    # The second segment is at latitude 0.01, so its geodesic length
    # is independently checked against the first and not assumed identical.
    distances = [s["horizontal_distance_m"] for s in dataset["segments"]]
    assert isclose(distances[0], expected_segment_distance, abs_tol=.001)
    assert 0 < distances[1] <= distances[0]
    assert isclose(
        report["statistics"]["total_distance_m"],
        sum(distances), abs_tol=1e-6,
    )
    assert report["statistics"]["ascent_m"] == 0
    assert report["statistics"]["descent_m"] == 0
    assert report["statistics"]["observed_elapsed_s"] == 180
    assert all(s["terrain_complete"] for s in dataset["segments"])
    assert all(s["timing_complete"] for s in dataset["segments"])
    assert all(p["dem_elevation_m"] == 100 for p in dataset["points"])
    assert all(
        p["recorded_time_text"] is not None for p in dataset["points"]
    )
    assert all(s["complete"] for s in sampling["sampling"]["segments"])
    assert all(s["complete"] for s in forecast["segments"])
    assert forecast["scenarios"][1]["moving_s"] is not None
    assert all(
        edge["predicted_moving_s"] is not None
        for edge in forecast["edges"]
    )
    assert source.read_bytes() == before
    for directory in outputs:
        manifest = _read(directory, "manifest.json")
        assert manifest["inputs"]["source"] == source_hash
        assert manifest["inputs"]["dem"] == sha256(dem.read_bytes()).hexdigest()
        for name, metadata in manifest["artifacts"].items():
            payload = (directory / name).read_bytes()
            assert metadata["bytes"] == len(payload)
            assert metadata["sha256"] == sha256(payload).hexdigest()


def test_without_dem_exposes_missing_terrain_without_inventing_forecast(tmp_path):
    """Missing DEM remains unknown across all products, never zero by default."""
    source = _source(tmp_path)
    output = tmp_path / "without-dem"
    run_pipeline(PipelineConfig(
        command="analyze", input_path=source, output_dir=output,
        forecast=True,
    ))
    dataset = _read(output, "analytical/dataset.json")
    route = _read(output, "analytical/route-analysis.json")
    forecast = _read(output, "analytical/activity-forecast.json")
    assert all(p["dem_elevation_m"] is None for p in dataset["points"])
    assert all(p["grade_percent"] is None for p in dataset["points"])
    assert route["statistics"]["ascent_m"] is None
    assert route["statistics"]["descent_m"] is None
    assert "PARTIAL_OR_UNAVAILABLE_TERRAIN" in route["diagnostics"]
    assert forecast["scenarios"][1]["moving_s"] is None
    assert "INCOMPLETE_FORECAST" in forecast["diagnostics"]
    assert "GRADE_UNAVAILABLE" in forecast["diagnostics"]
    assert "ASSUMED_GRADE_USED" not in forecast["diagnostics"]
    assert route["statistics"]["observed_elapsed_s"] == 180
    assert route["source_sha256"] == forecast["source_sha256"]
