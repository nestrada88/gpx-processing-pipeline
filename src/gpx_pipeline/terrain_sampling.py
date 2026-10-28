"""Terrain-adaptive analytical sampling without changing original GPX geometry.

Coordinates between original vertices are *geodesic interpolations*, not
reconstructed trail observations. All elevations are optional DEM samples.
The source analytical dataset and GPX remain immutable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isfinite
from typing import Callable

from geographiclib.geodesic import Geodesic

from .analytical import AnalyticalDataset
from .route_analysis import analyze_route
from .spatial import geodesic_distance_m


class SamplingError(ValueError):
    """Reject unsupported inputs or exceeded resource limits."""


@dataclass(frozen=True, slots=True)
class SamplingOptions:
    """Bound interpolated geodesic spacing and DEM curvature refinement."""

    max_spacing_m: float = 200.0
    elevation_residual_m: float = 2.0
    min_spacing_m: float = 5.0
    max_depth: int = 12
    max_output_points: int = 50_000

    def __post_init__(self) -> None:
        """Reject inconsistent spacing and unbounded work settings."""
        for value in (
            self.max_spacing_m, self.elevation_residual_m,
            self.min_spacing_m,
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError("Sampling thresholds must be finite and positive")
        if self.min_spacing_m > self.max_spacing_m:
            raise ValueError("min_spacing_m cannot exceed max_spacing_m")
        if type(self.max_depth) is not int or not 1 <= self.max_depth <= 24:
            raise ValueError("max_depth must be an integer from 1 to 24")
        if type(self.max_output_points) is not int or self.max_output_points < 1:
            raise ValueError("max_output_points must be a positive integer")


@dataclass(frozen=True, slots=True)
class SampledPoint:
    """Describe a source vertex or derived coordinate with explicit lineage."""

    kind: str
    index: int
    segment: int | None
    latitude: float
    longitude: float
    source_point_index: int | None
    original_edge_end_index: int | None
    edge_fraction: float | None
    distance_from_segment_start_m: float
    dem_elevation_m: float | None
    grade_from_previous_percent: float | None
    geometry_origin: str


@dataclass(frozen=True, slots=True)
class SampledSegment:
    """Hold independent interpolations for a single source segment."""

    kind: str
    index: int
    segment: int | None
    points: tuple[SampledPoint, ...]
    horizontal_distance_m: float
    dem_coverage_fraction: float
    complete: bool


@dataclass(frozen=True, slots=True)
class SamplingResult:
    """Expose bounded analytical samples, source fingerprint and diagnostics."""

    schema_version: str
    source_sha256: str
    dem_source_description: str
    options: SamplingOptions
    segments: tuple[SampledSegment, ...]
    diagnostics: tuple[str, ...]


def terrain_adaptive_sample(
    dataset: AnalyticalDataset,
    sample_elevation_m: Callable[[float, float], float | None],
    *,
    dem_source_description: str,
    options: SamplingOptions = SamplingOptions(),
) -> SamplingResult:
    """Densify recorded segments using geodesic spacing and DEM curvature.

    The callback must sample one consistent DEM and vertical datum, returning
    elevation in metres or None for unavailable coverage. This procedure only
    estimates coordinates along the WGS 84 geodesic between original vertices;
    it cannot discover bends or actual intermediate trail geometry.
    """
    analyze_route(dataset)
    if not callable(sample_elevation_m):
        raise TypeError("sample_elevation_m must be callable")
    if not isinstance(dem_source_description, str) or not dem_source_description.strip():
        raise ValueError("dem_source_description must be non-empty")
    grouped = {}
    for point in dataset.points:
        if point.kind in {"track", "route"}:
            grouped.setdefault(
                (point.kind, point.index, point.segment), []
            ).append(point)

    cache = {}
    output_count = 0
    diagnostics = set()

    def elevation(latitude, longitude):
        """Cache DEM samples and discard invalid or missing numeric output."""
        key = latitude, longitude
        if key not in cache:
            value = sample_elevation_m(latitude, longitude)
            if value is not None and (
                not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise SamplingError("DEM callback returned invalid elevation")
            cache[key] = float(value) if value is not None else None
        return cache[key]

    def consume():
        """Limit output even for adversarial geometry or DEM inputs."""
        nonlocal output_count
        output_count += 1
        if output_count > options.max_output_points:
            raise SamplingError("Adaptive samples exceed max_output_points")

    sampled_segments = []
    for segment in dataset.segments:
        identity = segment.kind, segment.index, segment.segment
        points = grouped.get(identity, [])
        emitted = []
        cumulative = 0.0

        def add(latitude, longitude, source_index, edge_end, fraction):
            """Append a uniquely identified sampled coordinate."""
            nonlocal cumulative
            height = elevation(latitude, longitude)
            if emitted:
                predecessor = emitted[-1]
                distance = geodesic_distance_m(
                    predecessor.latitude, predecessor.longitude,
                    latitude, longitude,
                )
                cumulative += distance
                grade = (
                    100 * (height - predecessor.dem_elevation_m) / distance
                    if distance > 0 and height is not None
                    and predecessor.dem_elevation_m is not None else None
                )
            else:
                grade = None
            consume()
            emitted.append(SampledPoint(
                segment.kind, segment.index, segment.segment,
                latitude, longitude, source_index, edge_end, fraction,
                cumulative, height, grade,
                "source_vertex" if source_index is not None
                else "geodesic_interpolation",
            ))

        if points:
            first = points[0]
            add(first.latitude, first.longitude, first.point, None, None)

        for left, right in zip(points, points[1:]):
            length = geodesic_distance_m(
                left.latitude, left.longitude, right.latitude, right.longitude,
            )
            inverse = Geodesic.WGS84.Inverse(
                left.latitude, left.longitude,
                right.latitude, right.longitude,
            )

            def position(fraction):
                """Find interpolated WGS84 coordinate along original edge."""
                result = Geodesic.WGS84.Direct(
                    left.latitude, left.longitude,
                    inverse["azi1"], length * fraction,
                )
                return result["lat2"], result["lon2"]

            def subdivide(lo, hi, start, finish, depth):
                """Refine long edges or DEM-residual curvature adaptively."""
                separation = length * (hi - lo)
                midpoint_fraction = (lo + hi) / 2
                midpoint = position(midpoint_fraction)
                heights = (
                    elevation(*start), elevation(*midpoint), elevation(*finish)
                )
                residual = (
                    abs(heights[1] - (heights[0] + heights[2]) / 2)
                    if all(height is not None for height in heights)
                    else None
                )
                if residual is None:
                    diagnostics.add("DEM_COVERAGE_INCOMPLETE")
                refine = (
                    separation > options.max_spacing_m
                    or (residual is not None
                        and residual > options.elevation_residual_m)
                )
                if not refine:
                    return []
                if depth >= options.max_depth or separation / 2 < options.min_spacing_m:
                    diagnostics.add("SAMPLING_RESOLUTION_LIMIT")
                    return []
                return (
                    subdivide(
                        lo, midpoint_fraction, start, midpoint, depth + 1
                    )
                    + [(midpoint_fraction, midpoint)]
                    + subdivide(
                        midpoint_fraction, hi, midpoint, finish, depth + 1
                    )
                )

            intermediate = subdivide(
                0.0, 1.0,
                (left.latitude, left.longitude),
                (right.latitude, right.longitude), 0,
            ) if length > 0 else []
            for fraction, (latitude, longitude) in intermediate:
                add(latitude, longitude, None, right.point, fraction)
            add(right.latitude, right.longitude, right.point, None, None)

        good = sum(p.dem_elevation_m is not None for p in emitted)
        coverage = good / len(emitted) if emitted else 0.0
        complete = bool(emitted) and good == len(emitted)
        sampled_segments.append(SampledSegment(
            segment.kind, segment.index, segment.segment,
            tuple(emitted), cumulative, coverage, complete,
        ))
    return SamplingResult(
        "1.0.0", dataset.source_sha256, dem_source_description,
        options, tuple(sampled_segments), tuple(sorted(diagnostics)),
    )


def terrain_sampling_json(result: SamplingResult) -> bytes:
    """Serialize deterministic, standards-compliant UTF-8 analytical JSON."""
    return (json.dumps(
        asdict(result), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ) + "\n").encode("utf-8")
