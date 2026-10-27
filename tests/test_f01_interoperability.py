"""Data-driven F01 interoperability and XML security checks."""

from pathlib import Path

import pytest

from gpx_pipeline import (
    GPXError,
    GPXLimits,
    GPXSchemaError,
    GPXSecurityError,
    SchemaRegistry,
    parse_gpx,
    serialize_gpx,
)

NS = "http://www.topografix.com/GPX/1/1"
XML = (
    f'<gpx xmlns="{NS}" version="1.1" creator="fixture">'
    '<trk><trkseg><trkpt lat="12.123456789" lon="-86.100000001">'
    '<ele>0012.50</ele></trkpt></trkseg></trk></gpx>'
).encode()


def test_round_trip_preserves_source_bytes_and_precision():
    """Return identical bytes without reformatting numbers or namespaces."""
    doc = parse_gpx(XML, strict=False)
    assert serialize_gpx(doc) == XML
    assert doc.tree()[0][0][0].get("lat") == "12.123456789"


def test_tree_access_is_detached():
    """Mutating a returned tree must not modify the stored source."""
    doc = parse_gpx(XML, strict=False)
    doc.tree()[0][0][0].set("lat", "0")
    assert doc.tree()[0][0][0].get("lat") == "12.123456789"


@pytest.mark.parametrize(
    "payload",
    [
        b'<gpx xmlns="urn:not-gpx"/>',
        b'<gpx/>',
        b'<notgpx/>',
    ],
)
def test_wrong_root_rejected(payload):
    """Reject incompatible namespace and root elements."""
    with pytest.raises(GPXSchemaError):
        parse_gpx(payload, strict=False)


def test_doctype_rejected():
    """Reject DTD input regardless of external entity resolution."""
    payload = (
        b'<!DOCTYPE gpx [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        + XML
    )
    with pytest.raises(GPXSecurityError):
        parse_gpx(payload, strict=False)


def test_resource_limits():
    """Enforce byte, node and depth limits."""
    with pytest.raises(GPXSecurityError):
        parse_gpx(XML, strict=False, limits=GPXLimits(max_bytes=10))
    with pytest.raises(GPXSecurityError):
        parse_gpx(XML, strict=False, limits=GPXLimits(max_nodes=2))
    with pytest.raises(GPXSecurityError):
        parse_gpx(XML, strict=False, limits=GPXLimits(max_depth=2))


def test_strict_requires_schema():
    """Fail closed if no official GPX schema is supplied."""
    with pytest.raises(GPXSchemaError, match="XSD path is required"):
        parse_gpx(XML)


def test_explicit_local_schema(tmp_path: Path):
    """Validate against an explicitly configured local XSD."""
    schema = tmp_path / "gpx.xsd"
    schema.write_text(
        f'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
          targetNamespace="{NS}" xmlns="{NS}"
          elementFormDefault="qualified">
          <xs:element name="gpx" type="xs:anyType"/>
          </xs:schema>''',
        encoding="utf-8",
    )
    doc = parse_gpx(XML, registry=SchemaRegistry(gpx11_xsd=schema))
    assert serialize_gpx(doc) == XML


def test_malformed_xml_rejected():
    """Reject incomplete XML."""
    with pytest.raises(GPXError):
        parse_gpx(b"<gpx", strict=False)
