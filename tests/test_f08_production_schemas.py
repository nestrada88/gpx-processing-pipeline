"""F08 pinned offline GPX 1.1 and Garmin extension XSD integration tests."""

from dataclasses import replace
from hashlib import sha256

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.production_schemas import (
    ProductionSchemaError, _SCHEMA_FILES, _compile_schemas,
    production_schema_registry, validate_production_gpx,
)

NS = "http://www.topografix.com/GPX/1/1"
GARMIN_TPX = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
GARMIN_GPX = "http://www.garmin.com/xmlschemas/GpxExtensions/v3"
GARMIN_POWER = "http://www.garmin.com/xmlschemas/PowerExtension/v1"


def gpx(inner, *, extra_ns=""):
    """Parse secure GPX without bypassing later real schema verification."""
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="F08" {extra_ns}>'
        f"{inner}</gpx>"
    ).encode()
    return parse_gpx(xml, strict=False)


def test_real_bundled_schema_compilation_and_registry():
    """Compile all pinned GPX/Garmin schema files without network access."""
    compiled = _compile_schemas()
    assert set(compiled) == set(_SCHEMA_FILES)
    reg = production_schema_registry()
    assert reg.gpx11_xsd.is_file()
    assert len(reg.extensions) == 8


def test_valid_source_without_extensions():
    """Require actual GPX 1.1 type and content semantics."""
    doc = gpx(
        '<wpt lat="12.4" lon="-86.3"><name>Checkpoint</name></wpt>'
        '<trk><name>Route</name><trkseg>'
        '<trkpt lat="12.4" lon="-86.3"/>'
        '<trkpt lat="12.5" lon="-86.4"/>'
        '</trkseg></trk>'
    )
    result = validate_production_gpx(doc)
    assert result.gpx11_valid
    assert result.extension_roots_validated == 0
    assert result.source_sha256 == sha256(doc.xml).hexdigest()


@pytest.mark.parametrize("content", [
    '<trk><trkseg><trkpt lat="12" lon="-86"/></trkseg><name>late</name></trk>',
    '<wpt lat="90.00001" lon="0"/>',
    '<wpt lat="12"/>',
    '<wpt lat="12" lon="-86"><ele>not-a-number</ele></wpt>',
    '<trk><trkseg><trkpt lat="12" lon="-86"><time>no-date</time></trkpt>'
    '<trkpt lat="13" lon="-87"/></trkseg></trk>',
])
def test_invalid_real_gpx_structures_fail(content):
    """Genuine GPX XSD rejects malformed coordinate and ordering structures."""
    with pytest.raises(ProductionSchemaError, match="GPX 1.1 XSD"):
        validate_production_gpx(gpx(content))


def test_valid_nested_garmin_trackpoint_extension():
    """Validate Garmin extension ROOT, not every nested child individually."""
    doc = gpx(
        '<trk><trkseg><trkpt lat="12" lon="-86">'
        '<extensions><gpxtpx:TrackPointExtension>'
        '<gpxtpx:hr>95</gpxtpx:hr>'
        '</gpxtpx:TrackPointExtension></extensions>'
        '</trkpt><trkpt lat="13" lon="-87"/></trkseg></trk>',
        extra_ns=f'xmlns:gpxtpx="{GARMIN_TPX}"',
    )
    result = validate_production_gpx(doc)
    assert result.extension_roots_validated == 1
    assert result.namespaces == (GARMIN_TPX,)


def test_invalid_garmin_trackpoint_child_fails():
    """Known namespace with invalid contents must fail actual Garmin schema."""
    doc = gpx(
        '<trk><trkseg><trkpt lat="12" lon="-86">'
        '<extensions><gpxtpx:TrackPointExtension>'
        '<gpxtpx:hr>not-a-heart-rate</gpxtpx:hr>'
        '</gpxtpx:TrackPointExtension></extensions>'
        '</trkpt><trkpt lat="13" lon="-87"/></trkseg></trk>',
        extra_ns=f'xmlns:gpxtpx="{GARMIN_TPX}"',
    )
    with pytest.raises(ProductionSchemaError, match="Garmin extension"):
        validate_production_gpx(doc)


def test_valid_power_extension():
    """Exercise Garmin power extension's global declaration."""
    doc = gpx(
        '<trk><trkseg><trkpt lat="12" lon="-86">'
        '<extensions><power:PowerInWatts>220</power:PowerInWatts></extensions>'
        '</trkpt><trkpt lat="13" lon="-87"/></trkseg></trk>',
        extra_ns=f'xmlns:power="{GARMIN_POWER}"',
    )
    result = validate_production_gpx(doc)
    assert result.extension_roots_validated == 1


def test_unknown_extension_namespace_fails_closed():
    """GPX lax wildcard acceptance cannot certify unknown namespaces."""
    doc = gpx(
        '<extensions><other:payload/></extensions>',
        extra_ns='xmlns:other="urn:unregistered"',
    )
    with pytest.raises(ProductionSchemaError, match="Unregistered"):
        validate_production_gpx(doc)


def test_known_namespace_undeclared_root_fails():
    """A nested complex-type child alone must not masquerade as root."""
    doc = gpx(
        '<trk><trkseg><trkpt lat="12" lon="-86">'
        '<extensions><gpxtpx:hr>91</gpxtpx:hr></extensions>'
        '</trkpt><trkpt lat="13" lon="-87"/></trkseg></trk>',
        extra_ns=f'xmlns:gpxtpx="{GARMIN_TPX}"',
    )
    with pytest.raises(ProductionSchemaError, match="Garmin extension"):
        validate_production_gpx(doc)


def test_invalid_resource_budget_fails_closed():
    """Existing F01 XML resource limits also bind production validation."""
    from gpx_pipeline import GPXLimits, GPXSecurityError
    doc = gpx('<trk><trkseg><trkpt lat="12" lon="-86"/>'
              '<trkpt lat="13" lon="-87"/></trkseg></trk>')
    with pytest.raises(GPXSecurityError):
        validate_production_gpx(doc, limits=GPXLimits(max_bytes=10))


def test_bundle_integrity_detects_mutation(monkeypatch):
    """Verify pinned bytes before trusting even a compilable schema."""
    from gpx_pipeline import production_schemas
    original = production_schemas._schema_bytes

    def corrupted(name):
        data = original(name)
        return data + b"\n" if name == "gpx.xsd" else data

    monkeypatch.setattr(production_schemas, "_schema_bytes", corrupted)
    with pytest.raises(ProductionSchemaError, match="integrity"):
        _compile_schemas()


def test_production_schemas_integrate_with_f07_export_verification():
    """Use bundled real XSDs for F07 source/export compatibility evidence."""
    from gpx_pipeline.garmin_export import export_garmin_navigation
    from gpx_pipeline.production_schemas import verify_production_garmin_export

    doc = gpx(
        '<trk><trkseg><trkpt lat="12" lon="-86"/>'
        '<trkpt lat="12.1" lon="-86.1"/></trkseg></trk>'
    )
    exported = export_garmin_navigation(doc)
    report = verify_production_garmin_export(doc, exported)
    assert report.schema_validated
    assert report.software_status == "validated"
    assert not report.physical_device_verified
