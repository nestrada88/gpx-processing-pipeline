"""F06 planned/recorded route comparison using geodesic polyline proximity.

Compare two immutable canonical datasets; trackpoint indices need not align.
A proximity match is not proof of route traversal or checkpoint completion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isclose, isfinite

from geographiclib.geodesic import Geodesic

from .analytical import AnalyticalDataset
from .route_analysis import analyze_route
from .spatial import geodesic_distance_m

_GEOD = Geodesic.WGS84


class ComparisonError(ValueError):
    """Reject incompatible datasets or excessive comparison workloads."""


@dataclass(frozen=True, slots=True)
class ComparisonOptions:
    """Bound geodesic matching and define off-route decision thresholds."""

    tolerance_m: float = 40.0
    max_pairs: int = 200_000
    max_reference_edge_m: float = 100_000.0
    planned_duration_s: float | None = None

    def __post_init__(self) -> None:
        """Validate physical thresholds and computational resource budgets."""
        if not isfinite(self.tolerance_m) or self.tolerance_m < 0:
            raise ValueError("tolerance_m must be finite and nonnegative")
        if (
            not isfinite(self.max_reference_edge_m)
            or self.max_reference_edge_m <= 0
        ):
            raise ValueError("max_reference_edge_m must be finite and positive")
        if type(self.max_pairs) is not int or self.max_pairs < 1:
            raise ValueError("max_pairs must be a positive integer")
        if self.planned_duration_s is not None and (
            not isfinite(self.planned_duration_s) or self.planned_duration_s <= 0
        ):
            raise ValueError("planned_duration_s must be finite and positive")


@dataclass(frozen=True, slots=True)
class PointMatch:
    """Express one recorded point's nearest planned geodesic feature."""

    track: int
    segment: int
    point: int
    deviation_m: float
    near_planned: bool
    planned_kind: str
    planned_index: int
    planned_segment: int | None
    planned_edge_end: int | None
    planned_edge_fraction: float | None
    elevation_difference_m: float | None


@dataclass(frozen=True, slots=True)
class OffRouteEvent:
    """Represent observed point-sampled divergence within one segment."""

    track: int
    segment: int
    start_point: int
    end_point: int
    rejoined: bool
    maximum_deviation_m: float


@dataclass(frozen=True, slots=True)
class CheckpointProximity:
    """Report a recorded vertex near a planned checkpoint, not a visit proof."""

    waypoint_index: int
    checkpoint_order: int | None
    closest_recorded_vertex_m: float | None
    within_tolerance: bool | None


@dataclass(frozen=True, slots=True)
class PlannedRecordedResult:
    """Store provenance, comparison diagnostics and bounded observations."""

    schema_version: str
    planned_sha256: str
    recorded_sha256: str
    planned_distance_m: float
    recorded_distance_m: float
    distance_difference_m: float
    sample_coverage_fraction: float | None
    max_deviation_m: float | None
    observed_elapsed_s: float | None
    duration_difference_s: float | None
    matches: tuple[PointMatch, ...]
    excursions: tuple[OffRouteEvent, ...]
    checkpoints: tuple[CheckpointProximity, ...]
    diagnostics: tuple[str, ...]


def _sequences(dataset):
    """Index independent tracks and routes without inventing connecting edges."""
    points = {}
    for point in dataset.points:
        if point.kind in {"track", "route"}:
            points.setdefault(
                (point.kind, point.index, point.segment), []
            ).append(point)
    for segment in dataset.segments:
        key = segment.kind, segment.index, segment.segment
        values = points.pop(key, [])
        if [p.point for p in values] != list(range(segment.point_count)):
            raise ComparisonError("Invalid point indexing")
        if any(
            not (isfinite(p.latitude) and isfinite(p.longitude))
            or abs(p.latitude) > 90 or abs(p.longitude) > 180
            for p in values
        ):
            raise ComparisonError("Invalid WGS 84 coordinates")
        yield key, values
    if points:
        raise ComparisonError("Unassociated geometry points")


def _reference_features(dataset, max_edge):
    """Create geodesic reference edges, including isolated single vertices."""
    features = []
    for key, points in _sequences(dataset):
        if len(points) == 1:
            features.append((key, points[0], points[0], None))
        for start, end in zip(points, points[1:]):
            edge = geodesic_distance_m(
                start.latitude, start.longitude, end.latitude, end.longitude
            )
            if edge > max_edge:
                raise ComparisonError("Reference edge exceeds configured limit")
            features.append((key, start, end, edge))
    return features


def _distance_to_feature(latitude, longitude, feature):
    """Minimize WGS 84 distance along a finite geodesic segment.

    Bounded golden-section search with endpoints gives sub-metre convergence
    for supported reference edges up to 100 km. Zero edges are vertices.
    """
    _, start, end, distance = feature
    if distance is None or distance == 0:
        return (
            geodesic_distance_m(
                latitude, longitude, start.latitude, start.longitude
            ), 0.0
        )
    inverse = _GEOD.Inverse(
        start.latitude, start.longitude, end.latitude, end.longitude
    )
    line = _GEOD.Line(start.latitude, start.longitude, inverse["azi1"])

    def evaluate(fraction):
        position = line.Position(distance * fraction)
        return geodesic_distance_m(
            latitude, longitude, position["lat2"], position["lon2"]
        )

    lo, hi = 0.0, 1.0
    phi = (5 ** 0.5 - 1) / 2
    a, b = hi - phi * (hi - lo), lo + phi * (hi - lo)
    fa, fb = evaluate(a), evaluate(b)
    for _ in range(38):
        if fa <= fb:
            hi, b, fb = b, a, fa
            a = hi - phi * (hi - lo)
            fa = evaluate(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + phi * (hi - lo)
            fb = evaluate(b)
    candidates = ((evaluate(0), 0.0), (evaluate(1), 1.0),
                  (fa, a), (fb, b))
    return min(candidates, key=lambda item: item[0])


def _elevation_difference(recorded, feature, fraction, compatible):
    """Compare compatible DEM elevations using linear along-edge interpolation."""
    if not compatible or recorded.dem_elevation_m is None:
        return None
    _, start, end, _ = feature
    if start.dem_elevation_m is None or end.dem_elevation_m is None:
        return None
    return recorded.dem_elevation_m - (
        start.dem_elevation_m +
        fraction * (end.dem_elevation_m - start.dem_elevation_m)
    )


def compare_planned_recorded(
    planned: AnalyticalDataset,
    recorded: AnalyticalDataset,
    *,
    options: ComparisonOptions = ComparisonOptions(),
) -> PlannedRecordedResult:
    """Calculate observed-point deviations against independent planned edges.

    A comparison reports proximity to the planned geometry, not completion,
    direction, topology equivalence, or coverage of the entire planned route.
    """
    planned_report = analyze_route(planned)
    recorded_report = analyze_route(recorded)
    features = _reference_features(planned, options.max_reference_edge_m)
    sequences = list(_sequences(recorded))
    observed = [
        point for (kind, _, _), points in sequences
        if kind == "track" for point in points
    ]
    if len(features) * len(observed) > options.max_pairs:
        raise ComparisonError("Geodesic comparison exceeds pair limit")
    diagnostics = []
    if not features:
        diagnostics.append("PLANNED_GEOMETRY_UNAVAILABLE")
    if not observed:
        diagnostics.append("RECORDED_TRACK_UNAVAILABLE")
    compatible_heights = (
        bool(planned.dem_vertical_datum)
        and planned.dem_vertical_datum == recorded.dem_vertical_datum
        and bool(planned.dem_source)
        and bool(recorded.dem_source)
    )
    if not compatible_heights:
        diagnostics.append("ELEVATION_COMPARISON_UNAVAILABLE")
    matches = []
    events = []
    for (kind, index, segment), points in sequences:
        if kind != "track":
            continue
        active = None
        for point in points:
            if not features:
                continue
            best = min(
                ((*_distance_to_feature(
                    point.latitude, point.longitude, feature
                ), feature) for feature in features),
                key=lambda item: item[0],
            )
            deviation, fraction, feature = best
            key, start, end, edge_length = feature
            near = deviation <= options.tolerance_m
            matches.append(PointMatch(
                track=index, segment=segment, point=point.point,
                deviation_m=deviation, near_planned=near,
                planned_kind=key[0], planned_index=key[1],
                planned_segment=key[2],
                planned_edge_end=end.point if edge_length is not None else None,
                planned_edge_fraction=(
                    fraction if edge_length is not None else None
                ),
                elevation_difference_m=_elevation_difference(
                    point, feature, fraction, compatible_heights
                ),
            ))
            if not near:
                if active is None:
                    active = [point.point, point.point, deviation]
                else:
                    active[1] = point.point
                    active[2] = max(active[2], deviation)
            elif active is not None:
                events.append(OffRouteEvent(
                    index, segment, active[0], active[1], True, active[2]
                ))
                active = None
        if active is not None:
            events.append(OffRouteEvent(
                index, segment, active[0], active[1], False, active[2]
            ))
    checkpoint_results = []
    planned_catalog = planned.waypoint_catalog
    if planned_catalog is not None:
        for waypoint in sorted(
            planned_catalog.entries,
            key=lambda item: (
                item.checkpoint_order is None,
                item.checkpoint_order or 0, item.index,
            ),
        ):
            distance = min(
                (geodesic_distance_m(
                    waypoint.latitude, waypoint.longitude,
                    point.latitude, point.longitude,
                ) for point in observed),
                default=None,
            )
            checkpoint_results.append(CheckpointProximity(
                waypoint.index, waypoint.checkpoint_order, distance,
                distance <= options.tolerance_m if distance is not None else None,
            ))
    if planned_catalog is None:
        diagnostics.append("PLANNED_CHECKPOINTS_UNAVAILABLE")
    timing = recorded_report.statistics.observed_elapsed_s
    if options.planned_duration_s is None:
        diagnostics.append("PLANNED_DURATION_UNAVAILABLE")
    if timing is None:
        diagnostics.append("RECORDED_DURATION_UNAVAILABLE")
    if any(event.rejoined for event in events):
        diagnostics.append("OBSERVED_REJOIN_DETECTED")
    return PlannedRecordedResult(
        schema_version="1.0.0",
        planned_sha256=planned.source_sha256,
        recorded_sha256=recorded.source_sha256,
        planned_distance_m=planned_report.statistics.total_distance_m,
        recorded_distance_m=recorded_report.statistics.total_distance_m,
        distance_difference_m=(
            recorded_report.statistics.total_distance_m -
            planned_report.statistics.total_distance_m
        ),
        sample_coverage_fraction=(
            sum(match.near_planned for match in matches) / len(matches)
            if matches else None
        ),
        max_deviation_m=max((match.deviation_m for match in matches),
                            default=None),
        observed_elapsed_s=timing,
        duration_difference_s=(
            timing - options.planned_duration_s
            if timing is not None and options.planned_duration_s is not None
            else None
        ),
        matches=tuple(matches),
        excursions=tuple(events),
        checkpoints=tuple(checkpoint_results),
        diagnostics=tuple(diagnostics),
    )


def planned_recorded_json(result: PlannedRecordedResult) -> bytes:
    """Serialize deterministic, finite-only UTF-8 JSON results."""
    return (json.dumps(asdict(result), sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode()
