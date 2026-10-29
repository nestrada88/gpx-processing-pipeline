"""FV-02 installed CLI acceptance for canonical, DEM, and forecast deliverables."""

from hashlib import sha256
import json
import shutil
import subprocess

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


NS = "http://www.topografix.com/GPX/1/1"


def _source(tmp_path):
    """Create two disconnected recorded segments and a named source waypoint."""
    source = tmp_path / "recorded.gpx"
    source.write_text(
        f'<gpx xmlns="{NS}" version="1.1" creator="fv02">'
        '<wpt lat="12" lon="-86"><name>Start</name></wpt>'
        '<trk><name>Recorded</name>'
        '<trkseg><trkpt lat="12" lon="-86"><ele>87</ele>'
        '<time>2026-01-01T08:00:00Z</time></trkpt>'
        '<trkpt lat="12" lon="-85.999"><ele>89</ele>'
        '<time>2026-01-01T08:01:00Z</time></trkpt></trkseg>'
        '<trkseg><trkpt lat="12.002" lon="-86"><ele>93</ele>'
        '<time>2026-01-01T08:03:00Z</time></trkpt>'
        '<trkpt lat="12.002" lon="-85.999"><ele>94</ele>'
        '<time>2026-01-01T08:04:00Z</time></trkpt></trkseg>'
        '</trk></gpx>',
        encoding="utf-8",
    )
    return source


def _dem(tmp_path):
    """Build a local, fixed-value raster with explicit metre vertical units."""
    path = tmp_path / "surface.tif"
    with rasterio.open(
        path, "w", driver="GTiff", count=1, width=16, height=16,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(-86.01, 12.01, .002, .002), nodata=-9999,
    ) as raster:
        raster.write(np.full((16, 16), 100, dtype="float32"), 1)
        raster.set_band_unit(1, "m")
    return path


def _cli(*args):
    """Verify the installed command, not just the in-process API."""
    executable = shutil.which("gpx-pipeline")
    assert executable, "Installed entrypoint required"
    return subprocess.run(
        [executable, *map(str, args)],
        capture_output=True, text=True, timeout=45, check=False,
    )


def _json(directory, name):
    return json.loads((directory / name).read_bytes())


def _assert_manifest(directory, source, dem=None):
    """Validate every published artifact byte count and digest independently."""
    manifest = _json(directory, "manifest.json")
    assert manifest["inputs"]["source"] == sha256(source.read_bytes()).hexdigest()
    if dem is not None:
        assert manifest["inputs"]["dem"] == sha256(dem.read_bytes()).hexdigest()
    else:
        assert "dem" not in manifest["inputs"]
    for relative, record in manifest["artifacts"].items():
        payload = (directory / relative).read_bytes()
        assert record["sha256"] == sha256(payload).hexdigest()
        assert record["bytes"] == len(payload)
    return manifest


def test_cli_analytical_source_geometry_and_recorded_data_are_immutable(tmp_path):
    """No inter-segment leap or replacement of recorded elevation/time."""
    source = _source(tmp_path)
    original = source.read_bytes()
    output = tmp_path / "base-analytics"
    result = _cli("analyze", source, "--output", output)
    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == original
    data = _json(output, "analytical/dataset.json")
    tracks = [p for p in data["points"] if p["kind"] == "track"]
    assert [(p["segment"], p["point"]) for p in tracks] == [
        (0, 0), (0, 1), (1, 0), (1, 1),
    ]
    assert [p["recorded_elevation_text"] for p in tracks] == [
        "87", "89", "93", "94",
    ]
    assert [p["recorded_time_text"] for p in tracks] == [
        "2026-01-01T08:00:00Z", "2026-01-01T08:01:00Z",
        "2026-01-01T08:03:00Z", "2026-01-01T08:04:00Z",
    ]
    assert all(p["dem_elevation_m"] is None for p in tracks)
    segments = [s for s in data["segments"] if s["kind"] == "track"]
    assert [(s["segment"], s["point_count"]) for s in segments] == [
        (0, 2), (1, 2),
    ]
    assert segments[0]["horizontal_distance_m"] > 0
    assert segments[1]["horizontal_distance_m"] > 0
    assert tracks[2]["cumulative_distance_m"] == 0
    assert data["source_sha256"] == sha256(original).hexdigest()
    catalog = data["waypoint_catalog"]
    assert catalog["entries"][0]["name"] == "Start"
    assert catalog["entries"][0]["latitude"] == 12
    assert catalog["entries"][0]["longitude"] == -86
    manifest = _assert_manifest(output, source)
    assert set(manifest["artifacts"]) == {
        "analytical/dataset.json", "analytical/route-analysis.json",
    }


@pytest.mark.parametrize("assume", [False, True])
def test_cli_forecast_missing_dem_requires_explicit_grade_assumption(
    tmp_path, assume,
):
    """Do not convert recorded timestamps or unobserved grade into forecasts."""
    source = _source(tmp_path)
    original = source.read_bytes()
    destination = tmp_path / f"forecast-{assume}"
    args = ["analyze", source, "--output", destination, "--forecast"]
    if assume:
        args.append("--assume-flat-grade")
    result = _cli(*args)
    assert result.returncode == 0, result.stderr
    forecast = _json(destination, "analytical/activity-forecast.json")
    nominal = next(s for s in forecast["scenarios"] if s["label"] == "nominal")
    if assume:
        assert nominal["moving_s"] is not None
        assert nominal["moving_s"] > 0
        assert "ASSUMED_GRADE_USED" in forecast["diagnostics"]
    else:
        assert nominal["moving_s"] is None
        assert "INCOMPLETE_FORECAST" in forecast["diagnostics"]
        assert "ASSUMED_GRADE_USED" not in forecast["diagnostics"]
    assert nominal["finish_time"] is None
    data = _json(destination, "analytical/dataset.json")
    assert data["source_sha256"] == sha256(original).hexdigest()
    assert source.read_bytes() == original
    _assert_manifest(destination, source)


def test_cli_dem_and_adaptive_sampling_are_separate_derived_products(tmp_path):
    """DEM heights and densified points never overwrite original GPX records."""
    source = _source(tmp_path)
    dem = _dem(tmp_path)
    original_source, original_dem = source.read_bytes(), dem.read_bytes()
    destination = tmp_path / "with-dem"
    result = _cli(
        "analyze", source, "--output", destination,
        "--dem", dem, "--adaptive-sampling", "--forecast",
    )
    assert result.returncode == 0, result.stderr
    data = _json(destination, "analytical/dataset.json")
    tracks = [p for p in data["points"] if p["kind"] == "track"]
    assert len(tracks) == 4
    assert all(p["dem_elevation_m"] == pytest.approx(100) for p in tracks)
    assert [p["recorded_elevation_text"] for p in tracks] == [
        "87", "89", "93", "94",
    ]
    assert data["dem_source"] == str(dem)
    sampling = _json(destination, "analytical/terrain-sampling.json")
    assert sampling["provenance"]["vertical_units"] == "m"
    sampled_segments = sampling["sampling"]["segments"]
    assert len(sampled_segments) == 2
    assert all(len(segment["points"]) > 2 for segment in sampled_segments)
    forecast = _json(destination, "analytical/activity-forecast.json")
    nominal = next(s for s in forecast["scenarios"] if s["label"] == "nominal")
    assert nominal["moving_s"] is not None
    assert "ASSUMED_GRADE_USED" not in forecast["diagnostics"]
    manifest = _assert_manifest(destination, source, dem)
    assert set(manifest["artifacts"]) == {
        "analytical/dataset.json", "analytical/route-analysis.json",
        "analytical/terrain-sampling.json", "analytical/activity-forecast.json",
    }
    assert source.read_bytes() == original_source
    assert dem.read_bytes() == original_dem
