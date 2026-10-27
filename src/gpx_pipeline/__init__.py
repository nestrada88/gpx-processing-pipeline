"""GPX processing pipeline foundation."""

from .interoperability import (
    GPX11_NAMESPACE,
    GPXDocument,
    GPXError,
    GPXLimits,
    GPXSchemaError,
    GPXSecurityError,
    SchemaRegistry,
    parse_gpx,
    serialize_gpx,
)

__all__ = [
    "GPX11_NAMESPACE",
    "GPXDocument",
    "GPXError",
    "GPXLimits",
    "GPXSchemaError",
    "GPXSecurityError",
    "SchemaRegistry",
    "parse_gpx",
    "serialize_gpx",
]
