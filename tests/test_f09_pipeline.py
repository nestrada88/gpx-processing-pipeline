"""F09 CLI and orchestration end-to-end regression tests."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from gpx_pipeline.cli import main
from gpx_pipeline.output import OutputError, publish_outputs
from gpx_pipeline.pipeline import PipelineError, run_pipeline
from gpx_pipeline.pipeline_config import PipelineConfig


def gpx(tmp_path, name="route.gpx", *, invalid=False):
    """Write two-point GPX 1.1 source into a local test directory."""
    file = tmp_path / name
    lat = "91" if invalid else "12.0"
    file.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" '
        'version="1.1" creator="f09">'
        '<wpt lat="12.0" lon="-86.0"><name>Start</name></wpt>'
        '<trk><name>Route</name><trkseg>'
        f'<trkpt lat="{lat}" lon="-86.0"/>'
        '<trkpt lat="12.01" lon="-86.01"/>'
        '</trkseg></trk></gpx>',
        encoding="utf-8",
    )
    return file


def test_validate_command_reports_json_and_no_output(tmp_path, capsys):
    """Run strict bundled XSD, spatial and chronological checks."""
    source = gpx(tmp_path)
    exit_code = main(["validate", str(source), "--format", "json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["sha256"] == sha256(source.read_bytes()).hexdigest()


def test_process_generates_primary_analytical_products(tmp_path):
    """No DEM creates explicit nullable elevation, not invented data."""
    source = gpx(tmp_path)
    output = tmp_path / "result"
    code = main(["process", str(source), "--output", str(output)])
    assert code == 0
    assert (output / "analytical/dataset.json").exists()
    assert (output / "analytical/route-analysis.json").exists()
    dataset = json.loads((output / "analytical/dataset.json").read_bytes())
    assert all(point["dem_elevation_m"] is None for point in dataset["points"])
    manifest = json.loads((output / "manifest.json").read_bytes())
    assert manifest["inputs"]["source"] == sha256(source.read_bytes()).hexdigest()
    assert len(manifest["artifacts"]) == 2


def test_forecast_requires_explicit_flat_assumption_for_estimated_time(tmp_path):
    """Simulated timing never becomes source timestamps."""
    source = gpx(tmp_path)
    output = tmp_path / "forecast"
    assert main([
        "analyze", str(source), "--output", str(output),
        "--forecast", "--assume-flat-grade",
    ]) == 0
    forecast = json.loads((output / "analytical/activity-forecast.json").read_bytes())
    assert "ASSUMED_GRADE_USED" in forecast["diagnostics"]
    dataset = json.loads((output / "analytical/dataset.json").read_bytes())
    assert all(p["recorded_time_text"] is None for p in dataset["points"])


def test_export_two_independent_garmin_files_and_verification(tmp_path):
    """Per-device navigation GPX and compatibility evidence are separate."""
    source = gpx(tmp_path)
    output = tmp_path / "navigation"
    assert main([
        "export", str(source), "--output", str(output),
        "--garmin", "etrex-se", "--garmin", "instinct-2x-tactical",
    ]) == 0
    assert (output / "navigation/etrex-se.gpx").exists()
    assert (output / "navigation/instinct-2x-tactical.gpx").exists()
    for device in ("etrex-se", "instinct-2x-tactical"):
        report = json.loads((output / f"verification/{device}.json").read_bytes())
        assert report["schema_validated"] is True
        assert report["physical_device_verified"] is False
        assert report["software_status"] in {"validated", "unverified"}


def test_compare_generates_single_comparison_file(tmp_path):
    """Independent planned/recorded inputs remain identifiable."""
    left = gpx(tmp_path, "planned.gpx")
    right = gpx(tmp_path, "recorded.gpx")
    output = tmp_path / "comparison"
    assert main([
        "compare", "--planned", str(left), "--recorded", str(right),
        "--output", str(output),
    ]) == 0
    assert (output / "comparison/planned-vs-recorded.json").exists()


def test_invalid_gpx_does_not_publish_files(tmp_path):
    """Invalid WGS84 coordinates must block all downstream processing."""
    source = gpx(tmp_path, invalid=True)
    output = tmp_path / "invalid"
    assert main(["process", str(source), "--output", str(output)]) == 3
    assert not output.exists()


def test_output_directory_is_never_overwritten(tmp_path):
    """Existing user data is protected from replacement."""
    source = gpx(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep")
    assert main(["process", str(source), "--output", str(output)]) == 6
    assert marker.read_text() == "keep"


def test_output_stage_rejects_traversal_and_preserves_destination(tmp_path):
    """Output manager must not permit directory escape."""
    output = tmp_path / "out"
    with pytest.raises(OutputError, match="Invalid output"):
        publish_outputs(
            output, {"../escape.txt": b"malicious"},
            command="process", inputs={},
        )
    assert not output.exists()
    assert not (tmp_path / "escape.txt").exists()


def test_invalid_cli_config_exit_code(tmp_path):
    """Invalid command dependency is a usage/configuration error."""
    source = gpx(tmp_path)
    assert main([
        "analyze", str(source), "--output", str(tmp_path / "out"),
        "--adaptive-sampling",
    ]) == 2


def test_missing_input_and_size_limits(tmp_path):
    """Missing inputs and explicitly exceeded byte limits fail closed."""
    source = gpx(tmp_path)
    assert main(["validate", str(tmp_path / "absent.gpx")]) == 4
    assert main([
        "validate", str(source), "--max-input-bytes", "4",
    ]) == 4


def test_pipeline_result_paths_and_repeatability(tmp_path):
    """Output hashes are stable across separately named destinations."""
    source = gpx(tmp_path)
    a = run_pipeline(PipelineConfig(
        command="analyze", input_path=source, output_dir=tmp_path / "first"
    ))
    b = run_pipeline(PipelineConfig(
        command="analyze", input_path=source, output_dir=tmp_path / "second"
    ))
    assert a.artifacts == b.artifacts
    assert (a.output_dir / "manifest.json").read_bytes() == (
        b.output_dir / "manifest.json"
    ).read_bytes()


def test_options_disallow_duplicate_devices(tmp_path):
    """Device targets cannot accidentally overwrite the same output."""
    with pytest.raises(ValueError, match="Duplicate"):
        PipelineConfig(
            command="export", input_path=gpx(tmp_path),
            output_dir=tmp_path / "out",
            garmin_devices=("etrex-se", "etrex-se"),
        )


def test_process_local_dem_and_adaptive_sampling(tmp_path):
    """Exercise the complete F03 raster to F06 derived-output pathway."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    source = gpx(tmp_path)
    dem = tmp_path / "terrain.tif"
    with rasterio.open(
        dem, "w", driver="GTiff", width=16, height=16, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(-86.02, 12.02, .002, .002),
        nodata=-9999,
    ) as raster:
        raster.write(np.full((16, 16), 100, dtype="float32"), 1)
        raster.set_band_unit(1, "m")
    output = tmp_path / "terrain-output"
    assert main([
        "process", str(source), "--dem", str(dem),
        "--adaptive-sampling", "--output", str(output),
    ]) == 0
    dataset = json.loads((output / "analytical/dataset.json").read_bytes())
    trackpoints = [p for p in dataset["points"] if p["kind"] == "track"]
    assert all(p["dem_elevation_m"] == 100 for p in trackpoints)
    derived = json.loads(
        (output / "analytical/terrain-sampling.json").read_bytes()
    )
    assert len(derived["sampling"]["segments"][0]["points"]) > 2
    assert derived["provenance"]["vertical_units"] == "m"
    manifest = json.loads((output / "manifest.json").read_bytes())
    assert manifest["inputs"]["dem"] == sha256(dem.read_bytes()).hexdigest()
