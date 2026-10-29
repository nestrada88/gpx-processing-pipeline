"""FV-01 installed CLI subprocess acceptance: arguments, statuses and outputs."""

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess


def _cli(*arguments):
    """Run the actual installed script with no in-process function shortcuts."""
    executable = shutil.which("gpx-pipeline")
    assert executable, "The CI/test environment must install the console script"
    return subprocess.run(
        [executable, *(str(item) for item in arguments)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _source(tmp_path):
    """Write a valid two-vertex source with fixed coordinates and provenance."""
    source = tmp_path / "input.gpx"
    source.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" '
        'version="1.1" creator="fv01">'
        '<trk><trkseg><trkpt lat="12" lon="-86"/>'
        '<trkpt lat="12.001" lon="-86.001"/>'
        '</trkseg></trk></gpx>',
        encoding="utf-8",
    )
    return source


def test_installed_cli_help_displays_required_subcommands():
    """Verify packaging exposes the executable and all five user commands."""
    result = _cli("--help")
    assert result.returncode == 0
    assert result.stderr == ""
    for command in ("validate", "analyze", "process", "export", "compare"):
        assert command in result.stdout


def test_validate_text_stdout_has_no_output_directory(tmp_path):
    """Default human output must not create artifacts or modify input."""
    source = _source(tmp_path)
    original = source.read_bytes()
    result = _cli("validate", source)
    assert result.returncode == 0
    assert result.stdout.strip() == (
        "Valid GPX 1.1; spatial and temporal checks passed"
    )
    assert result.stderr == ""
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input.gpx"]
    assert source.read_bytes() == original


def test_validate_json_is_machine_readable_and_source_linked(tmp_path):
    """The public CLI reports the exact SHA-256 of the validated file."""
    source = _source(tmp_path)
    result = _cli("validate", source, "--format", "json")
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "valid": True, "sha256": sha256(source.read_bytes()).hexdigest(),
    }


def test_analyze_publishes_report_and_prints_output_destination(tmp_path):
    """Confirm stdout destination, source immutability and manifest lineage."""
    source = _source(tmp_path)
    before = source.read_bytes()
    destination = tmp_path / "analytics"
    result = _cli("analyze", source, "--output", destination)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(destination)
    assert result.stderr == ""
    dataset = json.loads((destination / "analytical/dataset.json").read_text())
    assert len([p for p in dataset["points"] if p["kind"] == "track"]) == 2
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["inputs"]["source"] == sha256(before).hexdigest()
    assert source.read_bytes() == before


def test_missing_input_is_typed_failure_and_no_publication(tmp_path):
    """A nonexistent file returns the documented input failure code."""
    destination = tmp_path / "not-published"
    result = _cli("analyze", tmp_path / "missing.gpx", "--output", destination)
    assert result.returncode == 4
    assert "INPUT_UNAVAILABLE:" in result.stderr
    assert not destination.exists()


def test_input_limit_is_typed_failure_without_mutation(tmp_path):
    """The bound must be enforced before analysis or publication."""
    source = _source(tmp_path)
    before = source.read_bytes()
    destination = tmp_path / "not-published"
    result = _cli(
        "analyze", source, "--output", destination, "--max-input-bytes", "8",
    )
    assert result.returncode == 4
    assert "INPUT_LIMIT:" in result.stderr
    assert not destination.exists()
    assert source.read_bytes() == before


def test_invalid_geospatial_input_maps_to_validation_failure(tmp_path):
    """An out-of-range WGS84 point must reject analysis with exit code 3."""
    source = _source(tmp_path)
    source.write_bytes(source.read_bytes().replace(b'lat="12.001"', b'lat="91"'))
    destination = tmp_path / "not-published"
    result = _cli("analyze", source, "--output", destination)
    assert result.returncode == 3
    assert any(
        code in result.stderr for code in ("GPX_INVALID:", "SPATIAL_INVALID:")
    )
    assert not destination.exists()


def test_invalid_config_uses_exit_two_and_no_publication(tmp_path):
    """Adaptive sampling must not silently proceed without a DEM."""
    source = _source(tmp_path)
    destination = tmp_path / "not-published"
    result = _cli(
        "analyze", source, "--output", destination, "--adaptive-sampling",
    )
    assert result.returncode == 2
    assert "CONFIG_INVALID:" in result.stderr
    assert not destination.exists()


def test_duplicate_garmin_flags_are_rejected_as_config_error(tmp_path):
    """One output target cannot be specified twice and silently overwritten."""
    source = _source(tmp_path)
    destination = tmp_path / "not-published"
    result = _cli(
        "export", source, "--output", destination,
        "--garmin", "etrex-se", "--garmin", "etrex-se",
    )
    assert result.returncode == 2
    assert "Duplicate Garmin target" in result.stderr
    assert not destination.exists()


def test_unsupported_flag_is_argparse_error(tmp_path):
    """Unknown flags should receive argparse usage diagnostics."""
    source = _source(tmp_path)
    result = _cli("validate", source, "--nonexistent-option")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_existing_destination_is_never_replaced(tmp_path):
    """A user-owned output remains untouched after a rejected publication."""
    source = _source(tmp_path)
    destination = tmp_path / "existing"
    destination.mkdir()
    existing = destination / "owner.txt"
    existing.write_text("keep", encoding="utf-8")
    result = _cli("analyze", source, "--output", destination)
    assert result.returncode == 6
    assert "OUTPUT_FAILED:" in result.stderr
    assert existing.read_text(encoding="utf-8") == "keep"
    assert sorted(p.name for p in destination.iterdir()) == ["owner.txt"]
