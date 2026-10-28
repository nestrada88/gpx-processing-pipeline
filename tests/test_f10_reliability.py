"""F10 operational safety, fault injection, Garmin limits and field evidence."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.cli import main
from gpx_pipeline.field_evidence import (
    FieldEvidenceRecord, FieldObservation, field_evidence_json,
)
from gpx_pipeline.garmin_export import (
    NavigationExportOptions, export_garmin_navigation,
)
from gpx_pipeline.operational_verification import verify_device_readiness
from gpx_pipeline.output import OutputError, publish_outputs
from gpx_pipeline.spatial import geodesic_distance_m


NS = "http://www.topografix.com/GPX/1/1"


def source(trackpoints=2, segments=1, routes=0):
    """Construct valid independent track or route lines of bounded size."""
    trks = []
    for track in range(segments):
        pts = "".join(
            f'<trkpt lat="12.0" lon="{-86 + i * 0.000001:.6f}"/>'
            for i in range(trackpoints)
        )
        trks.append(f"<trk><trkseg>{pts}</trkseg></trk>")
    rtes = []
    for item in range(routes):
        points = "".join(
            f'<rtept lat="12" lon="{-86 + i * 0.000001:.6f}"/>'
            for i in range(2)
        )
        rtes.append(f"<rte>{points}</rte>")
    raw = (
        f'<gpx xmlns="{NS}" creator="test" version="1.1">'
        + "".join(trks + rtes) + "</gpx>"
    ).encode("utf-8")
    return parse_gpx(raw, strict=False)


def readiness(document, device="etrex-se"):
    """Build a source-preserving F07 result and independently audit device limits."""
    export = export_garmin_navigation(
        document, options=NavigationExportOptions(device_id=device)
    )
    return verify_device_readiness(document, export)


@pytest.mark.parametrize(("count", "expected"), [
    (2, True), (199, True), (200, True), (201, False),
    (10000, False),
])
def test_etrex_course_point_boundary(count, expected):
    """Explore imports up to 10k trackpoints, but eTrex courses cap at 200."""
    report = readiness(source(count))
    assert report.software_compatible is expected
    codes = {f.code for f in report.findings}
    assert ("ETREX_COURSE_POINT_LIMIT_EXCEEDED" in codes) != expected
    assert report.physical_transfer_verified is False
    assert report.physical_navigation_verified is False


def test_device_limit_is_per_line_not_total_across_two_courses():
    """Two separate 150-point source tracks are each within the point limit."""
    report = readiness(source(150, segments=2))
    assert report.software_compatible


def test_etrex_stored_course_capacity():
    """Device's 50-course storage bound must not be conflated with point count."""
    assert readiness(source(2, segments=50)).software_compatible
    fail = readiness(source(2, segments=51))
    assert not fail.software_compatible
    assert any(f.code == "ETREX_COURSE_COUNT_EXCEEDED" for f in fail.findings)


def test_instinct_limit_not_copied_from_etrex():
    """No invented 200-point Instinct 2X course ceiling."""
    report = readiness(source(201), "instinct-2x-tactical")
    assert report.software_compatible
    assert any(f.code == "INSTINCT_COURSE_LIMIT_UNVERIFIED"
               for f in report.findings)


def test_cli_rejects_overcapacity_without_publishing(tmp_path, capsys):
    """An eTrex overcapacity export never leaves apparently successful outputs."""
    gp = tmp_path / "long.gpx"
    gp.write_bytes(source(201).xml)
    dest = tmp_path / "navigation"
    result = main([
        "export", str(gp), "--garmin", "etrex-se",
        "--output", str(dest),
    ])
    assert result == 5
    assert "ETREX_COURSE_POINT_LIMIT_EXCEEDED" in capsys.readouterr().err
    assert not dest.exists()


def test_cli_preserves_analytical_priority_on_overcapacity(tmp_path):
    """Analyze accepts dense source that navigation export must reject."""
    gp = tmp_path / "long.gpx"
    gp.write_bytes(source(201).xml)
    dest = tmp_path / "analytical"
    assert main(["analyze", str(gp), "--output", str(dest)]) == 0
    dataset = json.loads((dest / "analytical/dataset.json").read_text())
    assert sum(p["kind"] == "track" for p in dataset["points"]) == 201


def test_cli_emits_operational_report(tmp_path):
    """Software readiness and unobserved hardware readiness stay distinct."""
    gp = tmp_path / "short.gpx"
    gp.write_bytes(source(2).xml)
    dest = tmp_path / "result"
    assert main([
        "export", str(gp), "--garmin", "etrex-se",
        "--output", str(dest),
    ]) == 0
    evidence = json.loads(
        (dest / "verification/etrex-se-operational.json").read_text()
    )
    assert evidence["software_compatible"]
    assert not evidence["physical_transfer_verified"]
    assert not evidence["physical_navigation_verified"]


def test_field_evidence_requires_observations_and_matching_hashes():
    """Human field observations must be bound to exact source/export files."""
    original = b"<gpx source />"
    output = b"<gpx export />"
    record = FieldEvidenceRecord(
        device_id="etrex-se", firmware="v5.0",
        transfer_workflow="explore-web-tracks",
        source_sha256=sha256(original).hexdigest(),
        export_sha256=sha256(output).hexdigest(),
        observations=(
            FieldObservation(
                "explore_connect_import", "passed",
                "local-test-log:device-001",
            ),
            FieldObservation("offline_navigation", "unverified", None),
        ),
    )
    assert record.matches(original, output)
    assert not record.matches(original, output + b"corrupt")
    assert json.loads(field_evidence_json(record))["observations"][1][
        "outcome"
    ] == "unverified"


def test_field_evidence_cannot_self_certify_without_reference():
    """No passed/failed physical test without explicit supporting evidence."""
    with pytest.raises(ValueError, match="evidence"):
        FieldObservation("offline_navigation", "passed", None)


@pytest.mark.parametrize("firmware, digest", [
    ("", "0" * 64), ("v2", "not-a-digest"),
])
def test_field_evidence_rejects_incomplete_identity(firmware, digest):
    """Firmware and SHA-256 are mandatory for reproducible field attribution."""
    with pytest.raises(ValueError):
        FieldEvidenceRecord(
            "etrex-se", firmware, "explore-web-tracks",
            digest, "1" * 64, (),
        )


def test_field_evidence_disallows_duplicate_checks():
    """Each field check has one recorded result per evidence bundle."""
    with pytest.raises(ValueError, match="Duplicate"):
        FieldEvidenceRecord(
            "etrex-se", "v1", "explore-web-tracks",
            "0" * 64, "1" * 64,
            (FieldObservation("offline_navigation", "unverified", None),
             FieldObservation("offline_navigation", "unverified", None)),
        )


def test_output_fault_injection_cleans_stage(tmp_path, monkeypatch):
    """Failure before atomic publication never leaves output or staging files."""
    import gpx_pipeline.output as output_module

    def fail_fsync(fd):
        raise OSError("simulated write interruption")

    monkeypatch.setattr(output_module.os, "fsync", fail_fsync)
    with pytest.raises(OutputError, match="Failed to publish"):
        publish_outputs(
            tmp_path / "result", {"analytical/dataset.json": b"{}"},
            command="analyze", inputs={"source": "0" * 64},
        )
    assert not (tmp_path / "result").exists()
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_output_determinism_across_independent_destinations(tmp_path):
    """Outputs and manifests are byte-identical for identical parameters."""
    source_hash = {"source": "a" * 64}
    content = {"analytical/example.json": b'{"value":1}\n'}
    publish_outputs(tmp_path / "a", content, command="analyze", inputs=source_hash)
    publish_outputs(tmp_path / "b", content, command="analyze", inputs=source_hash)
    assert (tmp_path / "a/manifest.json").read_bytes() == (
        tmp_path / "b/manifest.json"
    ).read_bytes()


def test_reference_geodesic_is_finite_and_segment_safe():
    """WGS84 numerical sanity reference with declared absolute tolerance."""
    from math import isclose
    # 1 degree on WGS84 equator is 111319.49079327357 metres.
    distance = geodesic_distance_m(0, 0, 0, 1)
    assert isclose(distance, 111319.49079327357, rel_tol=0, abs_tol=0.002)


def test_multisegment_conversion_remains_unverified():
    """Conformant multi-segment source does not imply faithful Garmin import."""
    from gpx_pipeline.interoperability import GPXDocument

    raw = (f'<gpx xmlns="{NS}" creator="test" version="1.1">'
           '<trk><trkseg><trkpt lat="12" lon="-86"/>'
           '<trkpt lat="12.1" lon="-86.1"/></trkseg>'
           '<trkseg><trkpt lat="12.2" lon="-86.2"/>'
           '<trkpt lat="12.3" lon="-86.3"/></trkseg></trk></gpx>').encode()
    report = readiness(GPXDocument(raw))
    assert report.software_compatible
    assert any(f.code == "ETREX_SEGMENT_CONVERSION_UNVERIFIED"
               for f in report.findings)
