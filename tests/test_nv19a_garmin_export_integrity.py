"""NV-19A Garmin software export verification failure-path contracts."""

from dataclasses import replace
from hashlib import sha256

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.garmin_compatibility import (
    GarminCompatibilityOptions, verify_garmin_export,
)
from gpx_pipeline.garmin_export import (
    export_garmin_navigation, NavigationExportOptions,
)

NS = "http://www.topografix.com/GPX/1/1"


def _pair():
    """Build a valid fixed-geometry source and conservative eTrex GPX export."""
    source = parse_gpx(
        (
            f'<gpx xmlns="{NS}" version="1.1" creator="nv19a">'
            '<wpt lat="0" lon="0"><name>Start</name></wpt>'
            '<trk><trkseg><trkpt lat="0" lon="0"/>'
            '<trkpt lat="0" lon="0.001"/></trkseg></trk></gpx>'
        ).encode(),
        strict=False,
    )
    return source, export_garmin_navigation(
        source, options=NavigationExportOptions(device_id="etrex-se")
    )


def _codes(report):
    return {finding.code for finding in report.findings}


def _resign(export, data):
    """Isolate semantic validation from the separate export byte-hash check."""
    return replace(
        export, gpx=data, export_sha256=sha256(data).hexdigest(),
    )


def test_source_geometry_mutation_rejected_even_with_matching_export_hash():
    """Re-signing altered exported bytes cannot conceal changed track geometry."""
    source, exported = _pair()
    original = serialize_gpx(source)
    modified = exported.gpx.replace(
        b'lon="0.001"', b'lon="0.002"', 1,
    )
    assert modified != exported.gpx
    report = verify_garmin_export(
        source, _resign(exported, modified),
        options=GarminCompatibilityOptions(require_xsd=False),
    )
    assert report.software_status == "incompatible"
    assert report.geometry is not None
    assert report.geometry.exact_coordinate_and_segment_match is False
    assert "NAVIGATION_GEOMETRY_OR_WAYPOINT_CHANGED" in _codes(report)
    assert serialize_gpx(source) == original


def test_corrupt_geometry_audit_manifest_is_independently_rejected():
    """A false audit cannot pass even when exported geometry is unchanged."""
    source, exported = _pair()
    tampered_audit = replace(exported.audit, geometry_fingerprint="0" * 64)
    report = verify_garmin_export(
        source, replace(exported, audit=tampered_audit),
        options=GarminCompatibilityOptions(require_xsd=False),
    )
    assert report.software_status == "incompatible"
    assert "GEOMETRY_AUDIT_MISMATCH" in _codes(report)
    assert report.geometry.exact_coordinate_and_segment_match is True


def test_missing_creator_header_is_reported_without_claiming_validity():
    """A re-signed export lacking the required header is not acceptable GPX."""
    source, exported = _pair()
    modified = exported.gpx.replace(
        b'creator="gpx-processing-pipeline/etrex-se"',
        b'creator=""',
    )
    assert modified != exported.gpx
    report = verify_garmin_export(
        source, _resign(exported, modified),
        options=GarminCompatibilityOptions(require_xsd=False),
    )
    assert report.software_status == "incompatible"
    assert "GPX_HEADER_INVALID" in _codes(report)


def test_unregistered_extension_namespace_is_an_incompatibility():
    """Core-GPX lax extension handling cannot imply Garmin extension support."""
    source, exported = _pair()
    modified = exported.gpx.replace(
        b"</gpx>",
        b'<extensions><vendor:flag xmlns:vendor="urn:nv19a:unknown">'
        b'1</vendor:flag></extensions></gpx>',
    )
    assert modified != exported.gpx
    report = verify_garmin_export(
        source, _resign(exported, modified),
        options=GarminCompatibilityOptions(require_xsd=False),
    )
    assert report.software_status == "incompatible"
    assert "EXTENSION_SCHEMA_UNAVAILABLE" in _codes(report)


def test_profile_workflow_mismatch_is_not_a_verified_transfer():
    """Correct output bytes cannot certify a transfer via the wrong software."""
    source, exported = _pair()
    report = verify_garmin_export(
        source, exported,
        options=GarminCompatibilityOptions(
            workflow="connect-course", require_xsd=False,
        ),
    )
    assert report.software_status == "incompatible"
    assert report.physical_device_verified is False
    assert "PROFILE_WORKFLOW_MISMATCH" in _codes(report)
