"""F07 offline compatibility verification: hashes, GPX, transfer limits."""

from dataclasses import replace
import json

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.garmin_compatibility import (
    GarminCompatibilityOptions, GarminSchemaRegistry,
    garmin_verification_json, verify_garmin_export,
)
from gpx_pipeline.garmin_export import (
    NavigationExportOptions, export_garmin_navigation,
)

NS = "http://www.topografix.com/GPX/1/1"


def gpx(*, track_points=2, route_points=0, waypoints=0, two_segments=False):
    """Construct bounded GPX fixtures with independent source structures."""
    wpts = "".join(
        f'<wpt lat="12" lon="-86"><name>W{i}</name></wpt>'
        for i in range(waypoints)
    )
    trk = ""
    if track_points:
        items = [
            f'<trkpt lat="12" lon="{-86 + i * 0.000001:.6f}"/>'
            for i in range(track_points)
        ]
        if two_segments and track_points > 1:
            trk = (
                "<trk><trkseg>" + items[0] + "</trkseg>"
                + "<trkseg>" + "".join(items[1:]) + "</trkseg></trk>"
            )
        else:
            trk = "<trk><trkseg>" + "".join(items) + "</trkseg></trk>"
    rte = ""
    if route_points:
        rte = "<rte>" + "".join(
            f'<rtept lat="12" lon="{-86 + i * .000001:.6f}"/>'
            for i in range(route_points)
        ) + "</rte>"
    return parse_gpx((
        f'<gpx xmlns="{NS}" version="1.1" creator="source">'
        f'{wpts}{rte}{trk}</gpx>'
    ).encode(), strict=False)


def run(source, *, workflow="explore-web-tracks", require_xsd=False,
        schemas=None, device="etrex-se", export=None):
    """Generate a device export and exercise the verifier."""
    result = export or export_garmin_navigation(
        source, options=NavigationExportOptions(device_id=device)
    )
    return verify_garmin_export(
        source, result,
        options=GarminCompatibilityOptions(
            workflow=workflow, require_xsd=require_xsd
        ),
        schemas=schemas,
    )


def schema(tmp_path):
    """Provide deliberately small local fixture XSD, NOT official GPX schema."""
    path = tmp_path / "fixture-gpx.xsd"
    path.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{NS}" xmlns:g="{NS}" '
        'elementFormDefault="qualified">'
        '<xs:element name="gpx"><xs:complexType><xs:sequence>'
        '<xs:any minOccurs="0" maxOccurs="unbounded" processContents="lax"/>'
        '</xs:sequence><xs:attribute name="version" type="xs:string" '
        'use="required"/><xs:attribute name="creator" type="xs:string" '
        'use="required"/></xs:complexType></xs:element></xs:schema>',
        encoding="utf-8",
    )
    return GarminSchemaRegistry(gpx11_xsd=path)


def test_exact_geometry_hash_and_manifest_references():
    """All source and export fingerprints are cross-checked."""
    source = gpx(two_segments=True)
    report = run(source)
    assert report.geometry.exact_coordinate_and_segment_match
    assert report.geometry.exact_waypoint_xml_match
    assert report.geometry.source_geometry_sha256 == (
        report.geometry.exported_geometry_sha256
    )
    assert report.transfer.within_known_limits
    assert not report.physical_device_verified
    assert report.software_status == "unverified"
    assert garmin_verification_json(report) == garmin_verification_json(run(source))
    assert json.loads(garmin_verification_json(report))["device_id"] == "etrex-se"


def test_missing_schema_default_fails_closed():
    """Default strict compatibility verification requires local XSD."""
    source = gpx()
    report = run(source, require_xsd=True)
    assert report.software_status == "incompatible"
    assert "REQUIRED_XSD_NOT_VALIDATED" in {f.code for f in report.findings}


def test_local_synthetic_schema_exercises_strict_validation(tmp_path):
    """A fixture XSD confirms verifier wiring, not official GPX conformance."""
    source = gpx()
    report = run(source, schemas=schema(tmp_path), require_xsd=True)
    assert report.schema_validated
    assert report.software_status == "validated"
    assert not report.physical_device_verified


def test_bad_xsd_reports_incompatibility(tmp_path):
    """Strict schema errors never downgrade silently to non-strict mode."""
    local = schema(tmp_path)
    local.gpx11_xsd.write_text("<not-an-xsd/>")
    report = run(gpx(), schemas=local, require_xsd=True)
    assert report.software_status == "incompatible"
    assert "GPX_XSD_INVALID" in {f.code for f in report.findings}


@pytest.mark.parametrize(("count", "workflow", "expected"), [
    (200, "explore-web-routes", True),
    (201, "explore-web-routes", False),
    (10000, "explore-web-tracks", True),
    (10001, "explore-web-tracks", False),
])
def test_explore_line_point_boundaries(count, workflow, expected):
    """Import-selected line mode governs route and track size."""
    source = gpx(track_points=count)
    report = run(source, workflow=workflow)
    assert report.transfer.within_known_limits is expected
    errors = {f.code for f in report.findings if f.severity == "error"}
    assert ("EXPLORE_LINE_LIMIT_EXCEEDED" in errors) is not expected


@pytest.mark.parametrize(("count", "expected"), [(500, True), (501, False)])
def test_explore_waypoint_import_boundaries(count, expected):
    """Explore website per-import limit is distinct from device capacity."""
    source = gpx(waypoints=count)
    report = run(source)
    assert report.transfer.within_known_limits is expected
    assert (
        "EXPLORE_WAYPOINT_IMPORT_LIMIT_EXCEEDED"
        in {f.code for f in report.findings}
    ) is not expected


def test_explore_import_as_tracks_applies_to_routes():
    """Explore selection treats route input as tracks and uses 10000 ceiling."""
    source = gpx(track_points=0, route_points=201)
    assert run(source, workflow="explore-web-tracks").transfer.within_known_limits
    assert not run(
        source, workflow="explore-web-routes"
    ).transfer.within_known_limits


def test_multisegment_track_conversion_is_unverified():
    """Explore route conversion may not preserve original track segmentation."""
    report = run(gpx(two_segments=True), workflow="explore-web-routes")
    assert report.software_status == "unverified"
    assert "SEGMENT_TO_ROUTE_CONVERSION_UNVERIFIED" in {
        f.code for f in report.findings
    }


def test_connect_unknown_limits_do_not_invent_numbers():
    """Connect transfer constraints cannot inherit Explore website ceilings."""
    source = gpx(track_points=201)
    report = run(
        source, workflow="connect-course", device="instinct-2x-tactical"
    )
    assert report.software_status == "unverified"
    assert report.transfer.within_known_limits is None
    assert report.transfer.route_points_limit is None
    assert "CONNECT_POINT_LIMIT_UNVERIFIED" in {
        f.code for f in report.findings
    }


def test_target_workflow_mismatch_rejected():
    """eTrex exports cannot be declared Connect-target compatible."""
    report = run(gpx(), workflow="connect-course")
    assert report.software_status == "incompatible"
    assert "PROFILE_WORKFLOW_MISMATCH" in {f.code for f in report.findings}


def test_tampered_export_payload_and_stale_manifest():
    """Independent recomputation detects modified bytes and stored digests."""
    source = gpx()
    export = export_garmin_navigation(source)
    tampered = replace(export, gpx=export.gpx.replace(b'-86.000000', b'-86.100000', 1))
    report = run(source, export=tampered)
    assert report.software_status == "incompatible"
    errors = {f.code for f in report.findings}
    assert "EXPORT_HASH_MISMATCH" in errors
    assert "NAVIGATION_GEOMETRY_OR_WAYPOINT_CHANGED" in errors


def test_tampered_source_and_checkpoint_manifest():
    """Corrupted provenance and checkpoint order fail closed."""
    source = gpx(waypoints=1)
    export = export_garmin_navigation(source)
    changed = replace(
        export, source_sha256="0" * 64, checkpoints=((1, 10),)
    )
    report = run(source, export=changed)
    assert report.software_status == "incompatible"
    codes = {f.code for f in report.findings}
    assert "SOURCE_HASH_MISMATCH" in codes
    assert "CHECKPOINT_MAP_INVALID" in codes


def test_corrupted_bytes_are_reported_not_raised():
    """Invalid XML remains a structured incompatibility finding."""
    source = gpx()
    export = export_garmin_navigation(source)
    report = run(source, export=replace(export, gpx=b"<bad"))
    assert report.software_status == "incompatible"
    assert "EXPORT_XML_INVALID" in {f.code for f in report.findings}


def test_unknown_extensions_cannot_claim_schema_success(tmp_path):
    """Unregistered extension namespaces must be reported even with lax XSD."""
    source = gpx()
    export = export_garmin_navigation(source)
    changed = export.gpx.replace(
        b"</gpx>", b'<extensions xmlns:x="urn:unknown">'
        b'<x:foo>1</x:foo></extensions></gpx>',
    )
    report = run(
        source, schemas=schema(tmp_path), require_xsd=True,
        export=replace(export, gpx=changed),
    )
    assert "EXTENSION_SCHEMA_UNAVAILABLE" in {
        finding.code for finding in report.findings
    }
    assert report.software_status == "incompatible"


def test_option_rejects_unrecognized_workflow():
    """Avoid automatic transfer-mode substitutions."""
    with pytest.raises(ValueError):
        GarminCompatibilityOptions(workflow="explore-app")
