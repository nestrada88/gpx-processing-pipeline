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

from .spatial import (
    SpatialFinding,
    SpatialOptions,
    SpatialResult,
    geodesic_distance_m,
    validate_spatial,
)
__all__ += [
    "SpatialFinding",
    "SpatialOptions",
    "SpatialResult",
    "geodesic_distance_m",
    "validate_spatial",
]

from .dem import (
    DEMError,
    DEMOptions,
    DEMProvenance,
    DEMResult,
    DEMSample,
    enrich_dem,
)
__all__ += [
    "DEMError",
    "DEMOptions",
    "DEMProvenance",
    "DEMResult",
    "DEMSample",
    "enrich_dem",
]

from .terrain import (
    ProfilePoint,
    SurfaceMetrics,
    TerrainError,
    TerrainFinding,
    TerrainResult,
    TerrainSegment,
    analyze_dem_surface,
    analyze_terrain,
)
__all__ += [
    "ProfilePoint",
    "SurfaceMetrics",
    "TerrainError",
    "TerrainFinding",
    "TerrainResult",
    "TerrainSegment",
    "analyze_dem_surface",
    "analyze_terrain",
]
