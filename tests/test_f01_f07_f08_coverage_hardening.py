"""Regression tests for F01 registered schemas, F07 export guards, F08 pins.

All test inputs are synthetic; no Garmin physical verification is inferred.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from gpx_pipeline import GPXSchemaError, SchemaRegistry, parse_gpx
from gpx_pipeline.garmin_export import (
    GarminExportError,
    NavigationExportOptions,
    export_garmin_navigation,
)
from gpx_pipeline.production_schemas import (
    ProductionSchemaError, _compile_schemas, validate_production_gpx,
)
from gpx_pipeline.waypoints import enrich_waypoints


NS = "http://www.topografix.com/GPX/1/1"
EXT = "urn:coverage-fixture"


def _source(inner: str, *, extra_ns: str = ""):
    """Produce a source parsed without prematurely assuming XSD validity."""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" xmlns:x="{EXT}" '
         f'version="1.1" creator="coverage" {extra_ns}>'
         f"{inner}</gpx>").encode(),
        strict=False,
    )


TRACK = (
    '<trk><trkseg><trkpt lat="12" lon="-86"/>'
    '<trkpt lat="12.01" lon="-86.01"/></trkseg></trk>'
)


@pytest.mark.parametrize("value,valid", [("valid", True), ("invalid", False)])
def test_f01_registered_extension_schema_accepts_only_declared_value(
    tmp_path: Path, value: str, valid: bool,
) -> None:
    """Exercise actual F01 extension XSD success and rejection branches."""
    root_xsd = tmp_path / "gpx.xsd"
    root_xsd.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{NS}" elementFormDefault="qualified">'
        '<xs:element name="gpx"><xs:complexType><xs:sequence>'
        '<xs:any minOccurs="0" maxOccurs="unbounded" '
        'processContents="lax"/>'
        '</xs:sequence><xs:attribute name="version" type="xs:string" '
        'use="required"/><xs:attribute name="creator" type="xs:string" '
        'use="required"/></xs:complexType></xs:element></xs:schema>',
        encoding="utf-8",
    )
    extension_xsd = tmp_path / "extension.xsd"
    extension_xsd.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{EXT}" elementFormDefault="qualified">'
        '<xs:element name="code"><xs:simpleType>'
        '<xs:restriction base="xs:string">'
        '<xs:enumeration value="valid"/>'
        '</xs:restriction></xs:simpleType></xs:element></xs:schema>',
        encoding="utf-8",
    )
    source = _source(f'<extensions><x:code>{value}</x:code></extensions>')
    registry = SchemaRegistry(
        gpx11_xsd=root_xsd, extensions={EXT: extension_xsd},
    )
    if valid:
        parsed = parse_gpx(source.xml, strict=True, registry=registry)
        assert parsed.xml == source.xml
    else:
        with pytest.raises(GPXSchemaError, match="Extension XSD"):
            parse_gpx(source.xml, strict=True, registry=registry)


@pytest.mark.parametrize(
    ("insert", "message"),
    [
        ('<trk><unexpected/>' + TRACK[len("<trk>"):], "Unsupported GPX element"),
        ('<trk><trkseg><unexpected/><trkpt lat="12" lon="-86"/>'
         '<trkpt lat="12.01" lon="-86.01"/></trkseg></trk>',
         "Unsupported GPX element"),
    ],
)
def test_f07_rejects_unsupported_track_structure(insert: str, message: str):
    """Safe export never silently discards unknown GPX children."""
    with pytest.raises(GarminExportError, match=message):
        export_garmin_navigation(_source(insert))


def test_f07_rejects_unregistered_nested_point_extension():
    """Point extensions cannot bypass explicit Garmin mapping."""
    source = _source(
        '<trk><trkseg><trkpt lat="12" lon="-86">'
        '<extensions><x:code>valid</x:code></extensions>'
        '</trkpt><trkpt lat="12.01" lon="-86.01"/></trkseg></trk>'
    )
    with pytest.raises(GarminExportError, match="Extensions"):
        export_garmin_navigation(source)


@pytest.mark.parametrize("bad_order", [0, True, -3])
def test_f07_rejects_tampered_checkpoint_order(bad_order):
    """Do not trust a post-enrichment catalog whose order was corrupted."""
    source = _source(
        '<wpt lat="12" lon="-86"><name>CP</name></wpt>' + TRACK
    )
    catalog = enrich_waypoints(source, checkpoints={0: 1})
    tampered = replace(catalog.entries[0], checkpoint_order=bad_order)
    with pytest.raises(GarminExportError, match="checkpoint order"):
        export_garmin_navigation(
            source, waypoints=replace(catalog, entries=(tampered,)),
        )


def test_f07_strict_export_with_bundled_real_gpx_schema():
    """Strict export preserves geometry without asserting device import."""
    from gpx_pipeline.production_schemas import production_schema_registry

    source = _source(TRACK)
    exported = export_garmin_navigation(
        source,
        options=NavigationExportOptions(require_strict_xsd=True),
        registry=production_schema_registry(),
    )
    assert exported.audit.exact_geometry_match
    assert "XSD_NOT_VERIFIED" not in {f.code for f in exported.findings}


def test_f08_missing_bundled_schema_fails_closed(monkeypatch):
    """No schema is downloaded or silently replaced when a pin is absent."""
    import gpx_pipeline.production_schemas as schemas

    original = schemas._schema_bytes

    def missing(name: str) -> bytes:
        if name == "gpx.xsd":
            raise FileNotFoundError(name)
        return original(name)

    monkeypatch.setattr(schemas, "_schema_bytes", missing)
    with pytest.raises(ProductionSchemaError, match="Missing bundled schema"):
        _compile_schemas()


def test_f08_validates_multiple_garmin_extension_roots():
    """Count separately validated global extension roots, not child nodes."""
    namespace = "http://www.garmin.com/xmlschemas/PowerExtension/v1"
    source = parse_gpx(
        (f'<gpx xmlns="{NS}" xmlns:p="{namespace}" '
         'version="1.1" creator="coverage">'
         '<trk><trkseg><trkpt lat="12" lon="-86">'
         '<extensions><p:PowerInWatts>120</p:PowerInWatts></extensions>'
         '</trkpt><trkpt lat="12.01" lon="-86.01">'
         '<extensions><p:PowerInWatts>121</p:PowerInWatts></extensions>'
         '</trkpt></trkseg></trk></gpx>').encode(),
        strict=False,
    )
    report = validate_production_gpx(source)
    assert report.extension_roots_validated == 2
    assert report.namespaces == (namespace,)
