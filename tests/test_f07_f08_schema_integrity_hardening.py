"""Regression checks for pinned schema trust and fail-closed Garmin exports."""

from dataclasses import replace
from hashlib import sha1

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.garmin_export import GarminExportError, export_garmin_navigation
from gpx_pipeline.production_schemas import ProductionSchemaError, _compile_schemas
from gpx_pipeline.waypoints import enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"
XS = "http://www.w3.org/2001/XMLSchema"
TRACK = (
    '<trk><trkseg><trkpt lat="12" lon="-86"/>'
    '<trkpt lat="12.01" lon="-86.01"/></trkseg></trk>'
)


def _source(children: str):
    """Create a well-formed, non-strict GPX fixture."""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" xmlns:x="urn:unregistered" '
         f'version="1.1" creator="coverage">{children}</gpx>').encode(),
        strict=False,
    )


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        (
            '<not-schema xmlns="http://www.w3.org/2001/XMLSchema"/>',
            "Not an XML Schema",
        ),
        (
            f'<xs:schema xmlns:xs="{XS}" targetNamespace="urn:incorrect"/>',
            "Wrong schema namespace",
        ),
        (
            f'<xs:schema xmlns:xs="{XS}" targetNamespace="{NS}">'
            '<xs:include schemaLocation="remote.xsd"/></xs:schema>',
            "External schema dependencies not supported",
        ),
        (
            f'<xs:schema xmlns:xs="{XS}" targetNamespace="{NS}">'
            '<xs:element name="gpx" type="xs:UndefinedType"/>'
            '</xs:schema>',
            "Cannot compile bundled schema",
        ),
    ],
)
def test_f08_rejects_untrusted_but_correctly_pinned_schema(
    monkeypatch: pytest.MonkeyPatch, schema: str, expected: str,
) -> None:
    """Test structural checks *after* successful cryptographic pin checking.

    A temporary single-schema registry and its matching Git-blob SHA isolate
    compilation from the real bundled files without changing their contents.
    """
    import gpx_pipeline.production_schemas as schemas

    data = schema.encode("utf-8")
    blob_sha = sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    monkeypatch.setattr(schemas, "_SCHEMA_FILES", {NS: ("fixture.xsd", blob_sha)})
    monkeypatch.setattr(schemas, "_schema_bytes", lambda name: data)
    with pytest.raises(ProductionSchemaError, match=expected):
        _compile_schemas()


def test_f07_rejects_foreign_namespace_under_track() -> None:
    """A foreign track child may not be silently dropped from Garmin output."""
    source = _source('<trk><x:unsupported/><trkseg>'
                     '<trkpt lat="12" lon="-86"/>'
                     '<trkpt lat="12.01" lon="-86.01"/>'
                     '</trkseg></trk>')
    with pytest.raises(GarminExportError, match="Unregistered extension namespace"):
        export_garmin_navigation(source)


def test_f07_rejects_checkpoint_catalog_length_mismatch() -> None:
    """A catalog with fewer entries than source waypoints is stale."""
    source = _source(
        '<wpt lat="12" lon="-86"><name>A</name></wpt>'
        '<wpt lat="12.01" lon="-86.01"><name>B</name></wpt>' + TRACK
    )
    catalog = enrich_waypoints(source, checkpoints={0: 1, 1: 2})
    with pytest.raises(GarminExportError, match="source count"):
        export_garmin_navigation(
            source, waypoints=replace(catalog, entries=catalog.entries[:1]),
        )


def test_f07_rejects_duplicate_checkpoint_order_after_enrichment() -> None:
    """Corrupted checkpoint orders cannot masquerade as an ordered route."""
    source = _source(
        '<wpt lat="12" lon="-86"><name>A</name></wpt>'
        '<wpt lat="12.01" lon="-86.01"><name>B</name></wpt>' + TRACK
    )
    catalog = enrich_waypoints(source, checkpoints={0: 1, 1: 2})
    second = replace(catalog.entries[1], checkpoint_order=1)
    with pytest.raises(GarminExportError, match="Duplicate checkpoint order"):
        export_garmin_navigation(
            source, waypoints=replace(
                catalog, entries=(catalog.entries[0], second),
            ),
        )
