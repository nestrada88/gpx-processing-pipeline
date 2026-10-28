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

from .temporal import (
    MovementEdge,
    TemporalError,
    TemporalFinding,
    TemporalOptions,
    TemporalResult,
    TemporalSegment,
    analyze_temporal,
)
__all__ += [
    "MovementEdge",
    "TemporalError",
    "TemporalFinding",
    "TemporalOptions",
    "TemporalResult",
    "TemporalSegment",
    "analyze_temporal",
]

from .waypoints import (
    WaypointCatalog,
    WaypointCatalogEntry,
    WaypointError,
    WaypointFinding,
    enrich_waypoints,
)
__all__ += [
    "WaypointCatalog",
    "WaypointCatalogEntry",
    "WaypointError",
    "WaypointFinding",
    "enrich_waypoints",
]

from .analytical import (
    AnalyticalDataset,
    AnalyticalDatasetError,
    AnalyticalPoint,
    AnalyticalSegment,
    analytical_json,
    build_analytical_dataset,
)
__all__ += [
    "AnalyticalDataset",
    "AnalyticalDatasetError",
    "AnalyticalPoint",
    "AnalyticalSegment",
    "analytical_json",
    "build_analytical_dataset",
]

from .route_analysis import (
    CheckpointAssociation,
    GradeDistribution,
    RouteAnalysisError,
    RouteAnalysisOptions,
    RouteAnalysisResult,
    RouteSegmentSummary,
    RouteStatistics,
    analyze_route,
    route_analysis_json,
)
__all__ += [
    "CheckpointAssociation",
    "GradeDistribution",
    "RouteAnalysisError",
    "RouteAnalysisOptions",
    "RouteAnalysisResult",
    "RouteSegmentSummary",
    "RouteStatistics",
    "analyze_route",
    "route_analysis_json",
]

from .planned_recorded import (
    CheckpointProximity,
    ComparisonError,
    ComparisonOptions,
    OffRouteEvent,
    PlannedRecordedResult,
    PointMatch,
    compare_planned_recorded,
    planned_recorded_json,
)
__all__ += [
    "CheckpointProximity",
    "ComparisonError",
    "ComparisonOptions",
    "OffRouteEvent",
    "PlannedRecordedResult",
    "PointMatch",
    "compare_planned_recorded",
    "planned_recorded_json",
]

from .activity_forecasting import (
    ActivityForecastResult,
    CheckpointETA,
    ForecastEdge,
    ForecastError,
    ForecastOptions,
    ForecastScenario,
    ForecastSegment,
    activity_forecast_json,
    forecast_activity,
    tobler_speed_kmh,
)
__all__ += [
    "ActivityForecastResult",
    "CheckpointETA",
    "ForecastEdge",
    "ForecastError",
    "ForecastOptions",
    "ForecastScenario",
    "ForecastSegment",
    "activity_forecast_json",
    "forecast_activity",
    "tobler_speed_kmh",
]

from .terrain_sampling import (
    SampledPoint,
    SampledSegment,
    SamplingError,
    SamplingOptions,
    SamplingResult,
    terrain_adaptive_sample,
    terrain_sampling_json,
)
__all__ += [
    "SampledPoint",
    "SampledSegment",
    "SamplingError",
    "SamplingOptions",
    "SamplingResult",
    "terrain_adaptive_sample",
    "terrain_sampling_json",
]
