"""FV-03 CLI-to-artifact comparison and independent Garmin export contracts."""

from hashlib import sha256
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess

from lxml import etree
import pytest


NS = "http://www.topografix.com/GPX/1/1"
DEVICES = ("etrex-se", "instinct-2x-tactical")


def _cli(*args):
    """Invoke installed entrypoint with separate process and captured status."""
    exe = shutil.which("gpx-pipeline")
    assert exe, "Install the package console script in the test environment"
    return subprocess.run(
        [exe, *map(str, args)], capture_output=True, text=True,
        timeout=45, check=False,
    )


def _json(destination, relative):
    return json.loads((destination / relative).read_bytes())


def _check_manifest(destination, inputs):
    manifest = _json(destination, "manifest.json")
    assert manifest["inputs"] == {
        name: sha256(path.read_bytes()).hexdigest()
        for name, path in inputs.items()
    }
    assert sorted(manifest["artifacts"]) == sorted(
        str(path.relative_to(destination))
        for path in destination.rglob("*") if path.is_file()
        and path.name != "manifest.json"
    )
    for relative, entry in manifest["artifacts"].items():
        data = (destination / relative).read_bytes()
        assert entry["sha256"] == sha256(data).hexdigest()
        assert entry["bytes"] == len(data)


def _gpx(path, coordinates, *, waypoint=True):
    """Write one GPX track with exact coordinate tokens and optional waypoint."""
    waypoint_xml = (
        '<wpt lat="0" lon="0"><name>Start</name></wpt>'
        if waypoint else ""
    )
    vertices = "".join(
        f'<trkpt lat="{lat}" lon="{lon}"><time>'
        f'{(datetime(2026, 1, 1, 8, tzinfo=timezone.utc) + timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>'
        for index, (lat, lon) in enumerate(coordinates)
    )
    path.write_text(
        f'<gpx xmlns="{NS}" version="1.1" creator="fv03">'
        f'{waypoint_xml}<trk><trkseg>{vertices}</trkseg></trk></gpx>',
        encoding="utf-8",
    )
    return path


def _geometry(root):
    """Collect exact source token strings and independent segment boundaries."""
    prefix = f"{{{NS}}}"
    return (
        tuple(
            tuple(
                tuple((p.get("lat"), p.get("lon"))
                      for p in segment.findall(prefix + "trkpt"))
                for segment in track.findall(prefix + "trkseg")
            ) for track in root.findall(prefix + "trk")
        ),
        tuple(
            tuple((p.get("lat"), p.get("lon"))
                  for p in route.findall(prefix + "rtept"))
            for route in root.findall(prefix + "rte")
        ),
        tuple(etree.tostring(wp, method="c14n")
              for wp in root.findall(prefix + "wpt")),
    )


def test_cli_compare_observed_excursion_rejoin_and_source_lineage(tmp_path):
    """A recorded deviation/rejoin is observed, not a fabricated traversal."""
    planned = _gpx(
        tmp_path / "planned.gpx", (("0", "0"), ("0", "0.002")),
    )
    recorded = _gpx(
        tmp_path / "recorded.gpx",
        (("0", "0.0002"), ("0.001", "0.001"), ("0", "0.0018")),
    )
    before = planned.read_bytes(), recorded.read_bytes()
    destination = tmp_path / "comparison"
    result = _cli(
        "compare", "--planned", planned, "--recorded", recorded,
        "--output", destination,
    )
    assert result.returncode == 0, result.stderr
    data = _json(destination, "comparison/planned-vs-recorded.json")
    assert data["planned_sha256"] == sha256(before[0]).hexdigest()
    assert data["recorded_sha256"] == sha256(before[1]).hexdigest()
    assert [m["near_planned"] for m in data["matches"]] == [
        True, False, True,
    ]
    assert len(data["excursions"]) == 1
    event = data["excursions"][0]
    assert (event["start_point"], event["end_point"], event["rejoined"]) == (
        1, 1, True,
    )
    assert "OBSERVED_REJOIN_DETECTED" in data["diagnostics"]
    assert "PLANNED_DURATION_UNAVAILABLE" in data["diagnostics"]
    assert data["duration_difference_s"] is None
    assert data["observed_elapsed_s"] == pytest.approx(120.0)
    assert tuple(p.read_bytes() for p in (planned, recorded)) == before
    _check_manifest(destination, {"planned": planned, "recorded": recorded})


def test_cli_dual_garmin_export_preserves_segment_and_waypoint_identity(tmp_path):
    """Both device-labeled files retain source coordinate tokens and waypoint XML."""
    source = _gpx(
        tmp_path / "navigation.gpx", (("0", "0"), ("0", "0.002")),
    )
    original = source.read_bytes()
    destination = tmp_path / "navigation-output"
    result = _cli(
        "export", source, "--output", destination,
        "--garmin", "etrex-se",
        "--garmin", "instinct-2x-tactical",
    )
    assert result.returncode == 0, result.stderr
    source_root = etree.fromstring(original)
    for device in DEVICES:
        exported = (destination / f"navigation/{device}.gpx").read_bytes()
        root = etree.fromstring(exported)
        assert _geometry(root) == _geometry(source_root)
        assert root.get("creator") == f"gpx-processing-pipeline/{device}"
        manifest = _json(destination, f"navigation/{device}-manifest.json")
        assert manifest["source_sha256"] == sha256(original).hexdigest()
        assert manifest["export_sha256"] == sha256(exported).hexdigest()
        verification = _json(destination, f"verification/{device}.json")
        readiness = _json(destination, f"verification/{device}-operational.json")
        assert verification["software_status"] in {"validated", "unverified"}
        assert verification["physical_device_verified"] is False
        assert readiness["software_compatible"] is True
        assert readiness["physical_transfer_verified"] is False
        assert readiness["physical_navigation_verified"] is False
    assert source.read_bytes() == original
    _check_manifest(destination, {"source": source})


def test_cli_e_trex_over_course_point_limit_blocks_publication(tmp_path):
    """The eTrex course point gate rejects rather than silently decimating."""
    source = _gpx(
        tmp_path / "long-track.gpx",
        tuple(("0", f"{index / 100000:.5f}") for index in range(201)),
        waypoint=False,
    )
    original = source.read_bytes()
    destination = tmp_path / "blocked"
    result = _cli(
        "export", source, "--output", destination, "--garmin", "etrex-se",
    )
    assert result.returncode == 5
    assert "GARMIN_INCOMPATIBLE:" in result.stderr
    assert "ETREX_COURSE_POINT_LIMIT_EXCEEDED" in result.stderr
    assert not destination.exists()
    assert source.read_bytes() == original


def test_cli_process_without_garmin_does_not_emit_device_outputs(tmp_path):
    """Analytics-first process has no implicit device GPX or transfer claims."""
    source = _gpx(
        tmp_path / "source.gpx", (("0", "0"), ("0", "0.002")),
    )
    destination = tmp_path / "analytics-only"
    result = _cli("process", source, "--output", destination)
    assert result.returncode == 0, result.stderr
    assert (destination / "analytical/dataset.json").is_file()
    assert not (destination / "navigation").exists()
    assert not (destination / "verification").exists()
    _check_manifest(destination, {"source": source})
