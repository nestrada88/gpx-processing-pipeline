"""Offline production GPX 1.1 and Garmin extension schema verification.

Schemas are pinned byte-for-byte as Git blobs, mirrored from published XSDs.
No runtime network requests or implicit XML schema fetching are permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1, sha256
from importlib.resources import files
from pathlib import Path

from lxml import etree

from .interoperability import GPXDocument, GPX11_NAMESPACE, GPXLimits, _read_xml


class ProductionSchemaError(ValueError):
    """Reject invalid schema material or nonconforming GPX/extension XML."""


# Git blob SHA-1 allows exact checking of upstream mirror bytes. This is
# a reproducible pin, not an assertion of live official-host equivalence.
_SCHEMA_FILES = {
    "http://www.topografix.com/GPX/1/1":
        ("gpx.xsd", "d9441f6b6967ccda2fcf672140cb1e71ebb2deca"),
    "http://www.garmin.com/xmlschemas/GpxExtensions/v3":
        ("GpxExtensionsv3.xsd", "04d39649151a80090d722bed7e4555e47d7b8f40"),
    "http://www.garmin.com/xmlschemas/TrackPointExtension/v1":
        ("TrackPointExtensionv1.xsd", "89ff2205edef0c3b9d2c291fe722a02a4256ca7d"),
    "http://www.garmin.com/xmlschemas/TrackPointExtension/v2":
        ("TrackPointExtensionv2.xsd", "3417edd3a7d5d6c4db94b081e2fcb51885e02ce8"),
    "http://www.garmin.com/xmlschemas/WaypointExtension/v1":
        ("WaypointExtensionv1.xsd", "16e6fd9bed548c95e2ccdd244d0101f2c7c8e09d"),
    "http://www.garmin.com/xmlschemas/TripExtensions/v1":
        ("TripExtensionsv1.xsd", "588d55de3ba43a6ecaf85c535cae245d218b3288"),
    "http://www.garmin.com/xmlschemas/PressureExtension/v1":
        ("PressureExtensionv1.xsd", "22c082bdb37e718b2145e1ef668f55dc7af4881f"),
    "http://www.garmin.com/xmlschemas/PowerExtension/v1":
        ("PowerExtensionv1.xsd", "53740583c6d081c18ec68e65fb41aa808600bdd5"),
    "http://www.garmin.com/xmlschemas/AdventuresExtensions/v1":
        ("AdventuresExtensionv1.xsd", "cded00dcfbfb2de7b872f8e3f207ead8daa2e3ca"),
}


@dataclass(frozen=True, slots=True)
class ProductionSchemaResult:
    """Describe completed strict GPX and registered extension validation."""

    source_sha256: str
    gpx11_valid: bool
    extension_roots_validated: int
    namespaces: tuple[str, ...]


def _schema_bytes(name: str) -> bytes:
    """Load schema as package data with no filesystem/network fallback."""
    return files("gpx_pipeline").joinpath("schemas", name).read_bytes()


def _compile_schemas() -> dict[str, etree.XMLSchema]:
    """Verify pins, namespaces and offline-only schema dependency graph."""
    schemas = {}
    for namespace, (name, expected_git_blob) in _SCHEMA_FILES.items():
        try:
            data = _schema_bytes(name)
        except (OSError, FileNotFoundError) as exc:
            raise ProductionSchemaError(f"Missing bundled schema: {name}") from exc
        git_blob = sha1(
            f"blob {len(data)}\0".encode("ascii") + data
        ).hexdigest()
        if git_blob != expected_git_blob:
            raise ProductionSchemaError(f"Schema integrity mismatch: {name}")
        try:
            tree = _read_xml(data, GPXLimits())
            root = tree.getroot()
            if root.tag != "{http://www.w3.org/2001/XMLSchema}schema":
                raise ProductionSchemaError(f"Not an XML Schema: {name}")
            if root.get("targetNamespace") != namespace:
                raise ProductionSchemaError(f"Wrong schema namespace: {name}")
            if root.xpath(
                "./xs:import|./xs:include|./xs:redefine|./xs:override",
                namespaces={"xs": "http://www.w3.org/2001/XMLSchema"},
            ):
                raise ProductionSchemaError(
                    f"External schema dependencies not supported: {name}"
                )
            schemas[namespace] = etree.XMLSchema(tree)
        except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
            raise ProductionSchemaError(
                f"Cannot compile bundled schema: {name}"
            ) from exc
    return schemas


def validate_production_gpx(
    document: GPXDocument,
    *,
    limits: GPXLimits = GPXLimits(),
) -> ProductionSchemaResult:
    """Validate GPX XSD and all extension root elements with known Garmin XSDs.

    Only the root of an extension subtree is independently XSD validated:
    recursively validating each descendant breaks legitimate complex types.
    Reject unregistered extension namespaces everywhere in the document.
    """
    schema_map = _compile_schemas()
    tree = _read_xml(document.xml, limits)
    gpx = schema_map[GPX11_NAMESPACE]
    if not gpx.validate(tree):
        raise ProductionSchemaError(
            f"GPX 1.1 XSD violation: {gpx.error_log.last_error}"
        )
    root = tree.getroot()
    examined = set()
    count = 0
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        namespace = etree.QName(element).namespace
        if namespace in {None, GPX11_NAMESPACE}:
            continue
        if namespace not in schema_map:
            raise ProductionSchemaError(
                f"Unregistered extension namespace: {namespace}"
            )
        examined.add(namespace)
        parent = element.getparent()
        if parent is not None and isinstance(parent.tag, str):
            parent_namespace = etree.QName(parent).namespace
            if parent_namespace == namespace:
                continue
            # A recognized extension cannot be inserted at an arbitrary GPX
            # location. GPX's XSD checks its outer extensions containers.
            if parent_namespace == GPX11_NAMESPACE and etree.QName(parent).localname != "extensions":
                raise ProductionSchemaError("Extension outside GPX extensions")
        schema = schema_map[namespace]
        if not schema.validate(etree.ElementTree(element)):
            raise ProductionSchemaError(
                f"Garmin extension XSD violation ({namespace}): "
                f"{schema.error_log.last_error}"
            )
        count += 1
    return ProductionSchemaResult(
        sha256(document.xml).hexdigest(), True, count,
        tuple(sorted(examined)),
    )


def production_schema_registry():
    """Provide pinned local paths for F07's legacy schema-registry API.

    Callers should use validate_production_gpx for full strict-known extension
    validation; F01 legacy per-element validation cannot replace it.
    """
    from .interoperability import SchemaRegistry
    root = Path(__file__).with_name("schemas")
    return SchemaRegistry(
        gpx11_xsd=root / "gpx.xsd",
        extensions={
            ns: root / name for ns, (name, _) in _SCHEMA_FILES.items()
            if ns != GPX11_NAMESPACE
        },
    )
