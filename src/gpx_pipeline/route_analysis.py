"""F06 route-wide reporting over the immutable canonical analytical dataset.

All route statistics are derived from existing point/segment records. No new
spatial, DEM, or temporal processing is performed. Missing data is never zero.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isclose, isfinite

from .analytical import AnalyticalDataset, AnalyticalPoint


class RouteAnalysisError(ValueError):
    """Reject inconsistent canonical analytical input or configurations."""


@dataclass(frozen=True, slots=True)
class RouteAnalysisOptions:
    """Configure deterministic signed-grade categories."""

    flat_grade_percent: float = 1.0

    def __post_init__(self) -> None:
        """Require a finite, nonnegative flat-grade threshold."""
        if not isfinite(self.flat_grade_percent) or self.flat_grade_percent < 0:
            raise ValueError("flat_grade_percent must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class GradeDistribution:
    """Count and distance-weight valid signed grade edges."""

    uphill_edges: int
    downhill_edges: int
    flat_edges: int
    undefined_edges: int
    uphill_distance_m: float
    downhill_distance_m: float
    flat_distance_m: float

    @property
    def valid_distance_m(self) -> float:
        """Return total traversed distance with valid grade information."""
        return self.uphill_distance_m + self.downhill_distance_m + self.flat_distance_m


@dataclass(frozen=True, slots=True)
class RouteSegmentSummary:
    """Describe one original track segment or GPX route independently."""

    kind: str
    index: int
    segment: int | None
    point_count: int
    distance_m: float
    ascent_m: float | None
    descent_m: float | None
    elevation_min_m: float | None
    elevation_max_m: float | None
    elevation_coverage: float
    terrain_complete: bool | None
    timed_distance_m: float | None
    observed_elapsed_s: float | None
    average_speed_m_s: float | None
    timing_complete: bool | None
    grades: GradeDistribution


@dataclass(frozen=True, slots=True)
class RouteStatistics:
    """Aggregate independently scoped route and track segment measurements."""

    tracks: int
    routes: int
    segments: int
    geometry_points: int
    waypoint_count: int
    total_distance_m: float
    ascent_m: float | None
    descent_m: float | None
    elevation_min_m: float | None
    elevation_max_m: float | None
    elevation_coverage: float
    observed_elapsed_s: float | None
    observed_timed_distance_m: float | None
    average_observed_speed_m_s: float | None
    grades: GradeDistribution


@dataclass(frozen=True, slots=True)
class CheckpointAssociation:
    """Reference F05 waypoint proximity, without asserting trail projection."""

    waypoint_index: int
    checkpoint_order: int | None
    category: str
    name: str | None
    nearest_vertex_m: float | None
    near_route_vertex: bool | None


@dataclass(frozen=True, slots=True)
class RouteAnalysisResult:
    """Contain source-keyed report metrics and completeness diagnostics."""

    schema_version: str
    source_sha256: str
    dem_source: str | None
    dem_vertical_datum: str | None
    statistics: RouteStatistics
    segments: tuple[RouteSegmentSummary, ...]
    checkpoints: tuple[CheckpointAssociation, ...]
    diagnostics: tuple[str, ...]


def _edge_lengths(points: list[AnalyticalPoint], distance: float) -> list[float]:
    """Validate monotonic per-segment cumulative distance and its total."""
    result: list[float] = []
    previous = 0.0
    for index, point in enumerate(points):
        current = point.cumulative_distance_m
        if current is None or not isfinite(current) or current < previous:
            raise RouteAnalysisError("Invalid cumulative segment distance")
        if index == 0 and not isclose(current, 0.0, abs_tol=1e-7):
            raise RouteAnalysisError("Segment must begin at zero distance")
        if index:
            result.append(current - previous)
        previous = current
    if not isclose(previous if points else 0.0, distance, abs_tol=1e-5):
        raise RouteAnalysisError("Point distances do not match segment length")
    return result


def _grade_distribution(
    points: list[AnalyticalPoint],
    edges: list[float],
    threshold: float,
) -> GradeDistribution:
    """Use physical edge length as weighting, not point count."""
    counts = [0, 0, 0, 0]
    lengths = [0.0, 0.0, 0.0]
    for point, length in zip(points[1:], edges):
        grade = point.grade_percent
        if grade is None or not isfinite(grade):
            counts[3] += 1
            continue
        if length == 0:
            raise RouteAnalysisError("Grade on zero-distance edge")
        bucket = 0 if grade > threshold else 1 if grade < -threshold else 2
        counts[bucket] += 1
        lengths[bucket] += length
    return GradeDistribution(*counts, *lengths)


def _summarize_segment(segment, points, options):
    """Calculate honest segment coverage and raw contiguous elevation changes."""
    if len(points) != segment.point_count:
        raise RouteAnalysisError("Segment point count mismatch")
    if [p.point for p in points] != list(range(len(points))):
        raise RouteAnalysisError("Segment point indices are not contiguous")
    edge_lengths = _edge_lengths(points, segment.horizontal_distance_m)
    if segment.terrain_complete is None and any(
        p.dem_elevation_m is not None or p.grade_percent is not None
        for p in points
    ):
        raise RouteAnalysisError("Terrain fields lack a terrain source")
    if segment.timing_complete is None and any(
        p.elapsed_from_previous_s is not None
        or p.observed_speed_m_s is not None for p in points
    ):
        raise RouteAnalysisError("Timing fields lack a temporal source")
    elevations = [p.dem_elevation_m for p in points]
    if any(v is not None and not isfinite(v) for v in elevations):
        raise RouteAnalysisError("Non-finite DEM elevation")
    if any(
        p.grade_percent is not None and not isfinite(p.grade_percent)
        for p in points
    ):
        raise RouteAnalysisError("Non-finite grade")
    valid_heights = [e for e in elevations if e is not None]
    coverage = len(valid_heights) / len(points) if points else 0.0
    if segment.terrain_complete is True and len(valid_heights) != len(points):
        raise RouteAnalysisError("Terrain marked complete but missing elevation")
    ascent = descent = 0.0
    for previous, current in zip(elevations, elevations[1:]):
        if previous is not None and current is not None:
            difference = current - previous
            ascent += max(difference, 0.0)
            descent += max(-difference, 0.0)
    # Raw partial totals are never advertised as complete ascent/descent.
    full_terrain = segment.terrain_complete is True
    elapsed = timed_distance = 0.0
    timed_edges = 0
    for point, edge_length in zip(points[1:], edge_lengths):
        seconds = point.elapsed_from_previous_s
        speed = point.observed_speed_m_s
        if seconds is None and speed is None:
            continue
        if seconds is None or speed is None:
            raise RouteAnalysisError("Inconsistent kinematic edge fields")
        if not isfinite(seconds) or seconds <= 0 or not isfinite(speed) or speed < 0:
            raise RouteAnalysisError("Invalid elapsed time or speed")
        if not isclose(speed * seconds, edge_length, rel_tol=1e-6, abs_tol=1e-6):
            raise RouteAnalysisError("Kinematics do not match geodesic distance")
        timed_edges += 1
        elapsed += seconds
        timed_distance += edge_length
    if segment.timing_complete is True and timed_edges != len(edge_lengths):
        raise RouteAnalysisError("Timing marked complete but timed edges missing")
    full_timing = segment.timing_complete is True
    return RouteSegmentSummary(
        kind=segment.kind,
        index=segment.index,
        segment=segment.segment,
        point_count=len(points),
        distance_m=segment.horizontal_distance_m,
        ascent_m=ascent if full_terrain else None,
        descent_m=descent if full_terrain else None,
        elevation_min_m=min(valid_heights) if valid_heights else None,
        elevation_max_m=max(valid_heights) if valid_heights else None,
        elevation_coverage=coverage,
        terrain_complete=segment.terrain_complete,
        timed_distance_m=timed_distance if full_timing else None,
        observed_elapsed_s=elapsed if full_timing else None,
        average_speed_m_s=(timed_distance / elapsed
                           if full_timing and elapsed > 0 else None),
        timing_complete=segment.timing_complete,
        grades=_grade_distribution(points, edge_lengths, options.flat_grade_percent),
    )


def analyze_route(
    dataset: AnalyticalDataset,
    *,
    options: RouteAnalysisOptions = RouteAnalysisOptions(),
) -> RouteAnalysisResult:
    """Report route aggregates from the canonical analytical dataset alone."""
    if dataset.schema_version != "1.0.0":
        raise RouteAnalysisError("Unsupported analytical dataset schema")
    keyed = {}
    waypoints = []
    for point in dataset.points:
        if point.kind == "waypoint":
            waypoints.append(point)
            continue
        if point.kind not in {"track", "route"}:
            raise RouteAnalysisError("Unknown geometry point type")
        keyed.setdefault((point.kind, point.index, point.segment), []).append(point)
    if len({(s.kind, s.index, s.segment) for s in dataset.segments}) != len(dataset.segments):
        raise RouteAnalysisError("Duplicate segment identities")
    expected = {(s.kind, s.index, s.segment) for s in dataset.segments}
    if set(keyed) - expected:
        raise RouteAnalysisError("Points reference unknown segments")
    summaries = tuple(
        _summarize_segment(
            segment, keyed.get((segment.kind, segment.index, segment.segment), []),
            options,
        ) for segment in dataset.segments
    )
    if dataset.waypoint_catalog is not None:
        catalog = dataset.waypoint_catalog.entries
        if len(catalog) != len(waypoints) or {
            item.index for item in catalog
        } != {item.index for item in waypoints}:
            raise RouteAnalysisError("Waypoint catalog indices do not match dataset")
        associations = tuple(
            CheckpointAssociation(
                item.index, item.checkpoint_order, item.category, item.name,
                item.nearest_vertex_m, item.near_route,
            ) for item in sorted(
                catalog, key=lambda item: (
                    item.checkpoint_order is None,
                    item.checkpoint_order or 0, item.index,
                )
            )
        )
    else:
        associations = ()
    total_points = sum(s.point_count for s in summaries)
    if total_points + len(waypoints) != len(dataset.points):
        raise RouteAnalysisError("Unaccounted analytical point records")
    complete_terrain = all(s.terrain_complete is True for s in summaries)
    complete_timing = all(
        s.timing_complete is True for s in summaries if s.kind == "track"
    )
    track_summaries = [s for s in summaries if s.kind == "track"]
    complete_timing = bool(track_summaries) and all(
        s.timing_complete is True for s in track_summaries
    )
    distances = sum(s.distance_m for s in summaries)
    complete_elapsed = sum(
        s.observed_elapsed_s or 0.0 for s in track_summaries
    )
    complete_timed_distance = sum(
        s.timed_distance_m or 0.0 for s in track_summaries
    )
    min_heights = [s.elevation_min_m for s in summaries
                   if s.elevation_min_m is not None]
    max_heights = [s.elevation_max_m for s in summaries
                   if s.elevation_max_m is not None]
    distribution = GradeDistribution(
        *(sum(getattr(s.grades, field) for s in summaries) for field in (
            "uphill_edges", "downhill_edges", "flat_edges", "undefined_edges",
            "uphill_distance_m", "downhill_distance_m", "flat_distance_m",
        ))
    )
    diagnostics = list(dataset.diagnostics)
    if not complete_terrain:
        diagnostics.append("PARTIAL_OR_UNAVAILABLE_TERRAIN")
    if not complete_timing:
        diagnostics.append("PARTIAL_OR_UNAVAILABLE_TRACK_TIMING")
    statistics = RouteStatistics(
        tracks=len({s.index for s in summaries if s.kind == "track"}),
        routes=len({s.index for s in summaries if s.kind == "route"}),
        segments=len(summaries),
        geometry_points=total_points,
        waypoint_count=len(waypoints),
        total_distance_m=distances,
        ascent_m=(sum(s.ascent_m or 0.0 for s in summaries)
                  if complete_terrain else None),
        descent_m=(sum(s.descent_m or 0.0 for s in summaries)
                   if complete_terrain else None),
        elevation_min_m=min(min_heights) if min_heights else None,
        elevation_max_m=max(max_heights) if max_heights else None,
        elevation_coverage=(
            sum(s.elevation_coverage * s.point_count for s in summaries) /
            total_points if total_points else 0.0
        ),
        observed_elapsed_s=complete_elapsed if complete_timing else None,
        observed_timed_distance_m=(
            complete_timed_distance if complete_timing else None
        ),
        average_observed_speed_m_s=(
            complete_timed_distance / complete_elapsed
            if complete_timing and complete_elapsed > 0 else None
        ),
        grades=distribution,
    )
    return RouteAnalysisResult(
        "1.0.0", dataset.source_sha256, dataset.dem_source,
        dataset.dem_vertical_datum, statistics, summaries, associations,
        tuple(diagnostics),
    )


def route_analysis_json(result: RouteAnalysisResult) -> bytes:
    """Serialize a deterministic standards-compliant UTF-8 JSON report."""
    return (json.dumps(
        asdict(result), sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":"),
    ) + "\n").encode("utf-8")
