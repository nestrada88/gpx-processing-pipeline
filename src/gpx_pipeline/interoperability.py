"""Secure GPX 1.1 ingestion and loss-aware XML serialization.

The immutable document stores validated XML bytes; callers receive new XML
trees on demand. Registered schema paths are local and explicitly configured.
This module does not fetch schemas or alter coordinate values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from lxml import etree

GPX11_NAMESPACE = "http://www.topografix.com/GPX/1/1"
GPX_TAG = f"{{{GPX11_NAMESPACE}}}gpx"


class GPXError(ValueError):
    """Represent an invalid GPX input or unsupported operation."""


class GPXSecurityError(GPXError):
    """Represent input rejected for XML security or resource limits."""


class GPXSchemaError(GPXError):
    """Represent a GPX or registered extension XSD validation error."""


@dataclass(frozen=True, slots=True)
class GPXLimits:
    """Define upper bounds on input and parsed XML resource usage."""

    max_bytes: int = 8_000_000
    max_nodes: int = 300_000
    max_depth: int = 64

    def __post_init__(self) -> None:
        """Reject nonpositive resource limits."""
        if min(self.max_bytes, self.max_nodes, self.max_depth) < 1:
            raise ValueError("All GPX resource limits must be positive")


@dataclass(frozen=True, slots=True)
class SchemaRegistry:
    """Reference local XSD files for GPX and registered extension namespaces."""

    gpx11_xsd: Path | None = None
    extensions: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GPXDocument:
    """Hold a preserved GPX XML snapshot with detached access to its tree."""

    xml: bytes

    def tree(self) -> etree._Element:
        """Return an independently parsed XML element tree."""
        return _read_xml(self.xml, GPXLimits(max_bytes=max(len(self.xml), 1))).getroot()


def _parser() -> etree.XMLParser:
    """Return a parser with external resolution and DTD loading disabled."""
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
        remove_comments=False,
        remove_pis=False,
        strip_cdata=False,
    )


def _read_xml(data: bytes, limits: GPXLimits) -> etree._ElementTree:
    """Parse bounded XML, refusing DTDs and unresolved entities."""
    if len(data) > limits.max_bytes:
        raise GPXSecurityError("GPX exceeds maximum XML byte count")
    try:
        tree = etree.parse(BytesIO(data), _parser())
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise GPXError(f"Invalid XML: {exc}") from exc

    if tree.docinfo.doctype:
        raise GPXSecurityError("DTD and entity declarations are prohibited")

    count = 0
    stack = [(tree.getroot(), 1)]
    while stack:
        element, depth = stack.pop()
        if not isinstance(element.tag, str):
            if isinstance(element, etree._Entity):
                raise GPXSecurityError("Unresolved XML entity")
            continue
        count += 1
        if count > limits.max_nodes or depth > limits.max_depth:
            raise GPXSecurityError("XML tree exceeds node or depth limit")
        stack.extend((child, depth + 1) for child in element)
    return tree


def _load_schema(path: Path) -> etree.XMLSchema:
    """Compile a locally supplied XSD without network resolution."""
    try:
        source = path.read_bytes()
        schema_tree = _read_xml(source, GPXLimits())
        return etree.XMLSchema(schema_tree)
    except (OSError, etree.XMLSchemaParseError, GPXError) as exc:
        raise GPXSchemaError(f"Cannot load XSD {path}: {exc}") from exc


def _validate(tree: etree._ElementTree, registry: SchemaRegistry) -> None:
    """Validate GPX 1.1 and configured registered extension elements."""
    if registry.gpx11_xsd is None:
        raise GPXSchemaError("GPX 1.1 XSD path is required for strict validation")
    schema = _load_schema(registry.gpx11_xsd)
    if not schema.validate(tree):
        raise GPXSchemaError(f"GPX 1.1 XSD: {schema.error_log.last_error}")

    for namespace, schema_path in sorted(registry.extensions.items()):
        extension_schema = _load_schema(schema_path)
        for element in tree.getroot().iter():
            if not isinstance(element.tag, str):
                continue
            if etree.QName(element).namespace == namespace:
                if not extension_schema.validate(etree.ElementTree(element)):
                    raise GPXSchemaError(
                        f"Extension XSD for {namespace}: "
                        f"{extension_schema.error_log.last_error}"
                    )


def parse_gpx(
    source: bytes,
    *,
    registry: SchemaRegistry | None = None,
    limits: GPXLimits = GPXLimits(),
    strict: bool = True,
) -> GPXDocument:
    """Parse and validate GPX; retain all XML content in a byte snapshot.

    Strict mode requires an explicit, local GPX 1.1 schema. Non-strict mode
    validates secure XML and the GPX root namespace only, not XSD structure.
    """
    tree = _read_xml(source, limits)
    root = tree.getroot()
    if root.tag != GPX_TAG:
        raise GPXSchemaError("Root must be GPX 1.1 in Topografix namespace")
    if strict:
        _validate(tree, registry or SchemaRegistry())
    return GPXDocument(xml=bytes(source))


def serialize_gpx(document: GPXDocument) -> bytes:
    """Return the preserved GPX source snapshot without rewriting values."""
    return bytes(document.xml)
