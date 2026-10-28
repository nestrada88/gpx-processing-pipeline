"""F07 Garmin GPX export and geometry-fidelity regression tests."""

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.garmin_export import (
    ETREX_SE, INSTINCT_2X_TACTICAL, GarminExportError,
    NavigationExportOptions, export_garmin_navigation, export_garmin_pair,
)
from gpx_pipeline.waypoints import enrich_waypoints

_NS = "http://www.topografix.com/GPX/1/1"


def document(*, waypoints="", geometry=None, extras=""):
    """Construct ordered GPX with two independent source track segments."""
    if geometry is None:
        geometry = (
            '<trk><name>Field route</name>'
            '<trkseg><trkpt lat="12.000000" lon="-86.000000"/>'
            '<trkpt lat="12.001000" lon="-86.002000"/>'
            '</trkseg><trkseg><trkpt lat="12.50000" lon="-86.50"/>'
            '<trkpt lat="12.51000" lon="-86.51"/></trkseg></trk>'
        )
    raw = (
        f'<gpx xmlns="{_NS}" creator="field" version="1.1">'
        f'{waypoints}{geometry}{extras}</gpx>'
    ).encode()
    return parse_gpx(raw, strict=False)


def test_pair_preserves_geometry_and_keeps_distinct_artifacts():
    """Each device receives independent bytes and identical source geometry."""
    original = document()
    before = serialize_gpx(original)
    handheld, watch = export_garmin_pair(original)
    assert handheld.profile == ETREX_SE
    assert watch.profile == INSTINCT_2X_TACTICAL
    assert handheld.gpx != watch.gpx
    assert handheld.audit.exact_geometry_match
    assert handheld.audit.geometry_fingerprint == watch.audit.geometry_fingerprint
    assert handheld.audit.track_segment_count == 2
    assert handheld.audit.trackpoint_count == 4
    assert handheld.source_sha256 == sha256(before).hexdigest()
    assert handheld.export_sha256 == sha256(handheld.gpx).hexdigest()
    assert serialize_gpx(original) == before


def test_reparse_and_stable_bytes():
    """Output is well-formed GPX 1.1 and deterministic by target."""
    input_data = document()
    left = export_garmin_navigation(input_data)
    right = export_garmin_navigation(input_data)
    assert left.gpx == right.gpx
    parsed = parse_gpx(left.gpx, strict=False)
    assert parsed.tree().get("creator") == (
        "gpx-processing-pipeline/etrex-se"
    )
    manifest = json.loads(left.manifest())
    assert manifest["audit"]["exact_geometry_match"] is True
    assert manifest["profile"]["device_id"] == "etrex-se"
    assert "gpx" not in manifest
    assert left.manifest() == right.manifest()


def test_checkpoint_order_preserves_waypoint_xml_order():
    """Explicit checkpoint sequence is metadata, not an XML reorder."""
    waypoints = (
        '<wpt lat="12" lon="-86"><name>B</name></wpt>'
        '<wpt lat="12.001" lon="-86.002"><name>A</name></wpt>'
    )
    source = document(waypoints=waypoints)
    catalog = enrich_waypoints(source, checkpoints={0: 2, 1: 1})
    result = export_garmin_navigation(source, waypoints=catalog)
    assert result.checkpoints == ((1, 1), (2, 0))
    parsed = parse_gpx(result.gpx, strict=False).tree()
    names = [
        item.findtext(f"{{{_NS}}}name")
        for item in parsed.findall(f"{{{_NS}}}wpt")
    ]
    assert names == ["B", "A"]


def test_catalog_mismatch_rejected():
    """Do not export stale checkpoint coordinates or waypoint identities."""
    source = document(waypoints='<wpt lat="12" lon="-86"><name>CP</name></wpt>')
    catalog = enrich_waypoints(source, checkpoints={0: 1})
    corrupted = replace(catalog.entries[0], latitude=11.9)
    with pytest.raises(GarminExportError, match="catalog"):
        export_garmin_navigation(
            source, waypoints=replace(catalog, entries=(corrupted,))
        )


def test_known_and_unknown_profile_limits_are_distinguished():
    """Reject only capacity constraints backed by the selected profile."""
    waypoints = "".join(
        f'<wpt lat="12" lon="-86"><name>W{i}</name></wpt>'
        for i in range(1001)
    )
    source = document(waypoints=waypoints)
    with pytest.raises(GarminExportError, match="capacity"):
        export_garmin_navigation(source)
    watch = export_garmin_navigation(
        source, options=NavigationExportOptions(
            device_id="instinct-2x-tactical"
        ),
    )
    assert any(
        finding.code == "WAYPOINT_LIMIT_UNKNOWN"
        for finding in watch.findings
    )


def test_route_geometry_supported_without_synthetic_track():
    """Keep routes as routes and avoid an implicit route-to-track conversion."""
    source = document(geometry=(
        '<rte><name>Route</name><rtept lat="12" lon="-86"/>'
        '<rtept lat="12.01" lon="-86.01"/></rte>'
    ))
    result = export_garmin_navigation(source)
    assert result.audit.track_count == 0
    assert result.audit.route_count == 1
    assert result.audit.routepoint_count == 2


@pytest.mark.parametrize("geometry", [
    "",
    '<trk><trkseg><trkpt lat="12" lon="-86"/></trkseg></trk>',
    '<trk><trkseg></trkseg></trk>',
])
def test_no_navigable_geometry_fails_closed(geometry):
    """Empty or one-point sources cannot be silently called courses."""
    with pytest.raises(GarminExportError, match="No navigable"):
        export_garmin_navigation(document(geometry=geometry))


def test_invalid_spatial_coordinates_rejected():
    """Existing F02 validation gates invalid WGS84 coordinates."""
    source = document(geometry=(
        '<trk><trkseg><trkpt lat="91" lon="-86"/>'
        '<trkpt lat="12" lon="-86"/></trkseg></trk>'
    ))
    with pytest.raises(GarminExportError, match="F02"):
        export_garmin_navigation(source)


def test_unknown_extension_fails_closed():
    """Never drop unknown Garmin or third-party extension content silently."""
    source = parse_gpx((
        f'<gpx xmlns="{_NS}" version="1.1" creator="field" '
        'xmlns:unknown="urn:unsupported"><trk><trkseg>'
        '<trkpt lat="12" lon="-86"/><trkpt lat="13" lon="-87"/>'
        '</trkseg></trk><extensions><unknown:custom>1</unknown:custom>'
        '</extensions></gpx>'
    ).encode(), strict=False)
    with pytest.raises(GarminExportError, match="Extensions"):
        export_garmin_navigation(source)


def test_unordered_children_fail_closed():
    """Do not claim schema compliance for malformed element ordering."""
    source = document(geometry=(
        '<trk><trkseg><trkpt lat="12" lon="-86"/>'
        '<trkpt lat="13" lon="-87"/></trkseg><name>after</name></trk>'
    ))
    with pytest.raises(GarminExportError, match="order"):
        export_garmin_navigation(source)


def test_strict_xsd_requires_local_registry():
    """Explicit strict XSD mode cannot silently downgrade validation."""
    with pytest.raises(GarminExportError, match="XSD"):
        export_garmin_navigation(
            document(),
            options=NavigationExportOptions(require_strict_xsd=True),
        )


def test_unverified_garmin_behaviors_visible():
    """Do not claim import success, geometry preservation after conversion or alerts."""
    result = export_garmin_navigation(document())
    codes = {finding.code for finding in result.findings}
    assert "DEVICE_TRANSFER_UNVERIFIED" in codes
    assert "COURSE_CONVERSION_UNVERIFIED" in codes
    assert "NAVIGATION_ALERTS_UNVERIFIED" in codes
    assert "XSD_NOT_VERIFIED" in codes


def test_unknown_profile_rejected():
    """The profile set cannot silently fall back to another device."""
    with pytest.raises(ValueError, match="profile"):
        NavigationExportOptions(device_id="etrex-legacy")
