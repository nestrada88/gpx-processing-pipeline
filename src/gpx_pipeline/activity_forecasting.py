"""F06 deterministic terrain-aware activity forecasts from canonical data.

All forecast values are simulated, never reconstructed as GPX observations.
Disconnected segments have independently computed travel times; no connecting
geometry, transfer time, or implicit start time is invented.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from math import exp, isfinite

from .analytical import AnalyticalDataset
from .route_analysis import analyze_route


class ForecastError(ValueError):
    """Reject inconsistent analytical input or unsupported forecast conditions."""


@dataclass(frozen=True, slots=True)
class ForecastOptions:
    """Configure Tobler's walking model and explicit uncertainty scenarios."""

    missing_grade: str = "unavailable"
    assumed_grade_percent: float = 0.0
    min_speed_kmh: float = 0.3
    max_speed_kmh: float = 8.0
    rest_seconds: float = 0.0
    optimistic_factor: float = 0.8
    conservative_factor: float = 1.3
    start_time: datetime | None = None

    def __post_init__(self) -> None:
        """Validate finite bounds, scenario ordering and aware start times."""
        if self.missing_grade not in {"unavailable", "assume"}:
            raise ValueError("missing_grade must be unavailable or assume")
        values = (
            self.assumed_grade_percent, self.min_speed_kmh,
            self.max_speed_kmh, self.rest_seconds,
            self.optimistic_factor, self.conservative_factor,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("Forecast parameters must be finite")
        if self.min_speed_kmh <= 0 or self.max_speed_kmh < self.min_speed_kmh:
            raise ValueError("Speed limits must be positive and ordered")
        if self.rest_seconds < 0:
            raise ValueError("Rest seconds must be nonnegative")
        if not (0 < self.optimistic_factor <= 1 <= self.conservative_factor):
            raise ValueError("Scenario factors must bracket nominal duration")
        if self.start_time is not None and (
            not isinstance(self.start_time, datetime)
            or self.start_time.tzinfo is None
            or self.start_time.utcoffset() is None
        ):
            raise ValueError("start_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ForecastEdge:
    """Represent one simulated distance-time interval."""

    kind: str
    index: int
    segment: int | None
    end_point: int
    distance_m: float
    grade_percent: float | None
    grade_assumed: bool
    predicted_speed_kmh: float | None
    predicted_moving_s: float | None


@dataclass(frozen=True, slots=True)
class ForecastSegment:
    """Describe forecastable coverage within an original segment."""

    kind: str
    index: int
    segment: int | None
    point_count: int
    distance_m: float
    moving_s: float | None
    forecastable_distance_m: float
    complete: bool


@dataclass(frozen=True, slots=True)
class ForecastScenario:
    """Describe an explicitly hypothetical time scenario."""

    label: str
    moving_s: float | None
    rest_s: float
    elapsed_s: float | None
    finish_time: str | None


@dataclass(frozen=True, slots=True)
class CheckpointETA:
    """Associate an exact ordered source vertex with a simulated arrival."""

    waypoint_index: int
    checkpoint_order: int
    kind: str
    index: int
    segment: int | None
    point: int
    elapsed_s: float
    arrival_time: str | None


@dataclass(frozen=True, slots=True)
class ActivityForecastResult:
    """Carry scenario outputs, provenance and explicit missing-data status."""

    schema_version: str
    source_sha256: str
    model: str
    model_version: str
    dem_source: str | None
    dem_vertical_datum: str | None
    options: ForecastOptions
    edges: tuple[ForecastEdge, ...]
    segments: tuple[ForecastSegment, ...]
    scenarios: tuple[ForecastScenario, ...]
    checkpoints: tuple[CheckpointETA, ...]
    diagnostics: tuple[str, ...]


def tobler_speed_kmh(
    grade_percent: float,
    *,
    min_speed_kmh: float = 0.3,
    max_speed_kmh: float = 8.0,
) -> float:
    """Calculate bounded Tobler speed from a signed percentage grade."""
    if not all(isfinite(v) for v in (
        grade_percent, min_speed_kmh, max_speed_kmh
    )):
        raise ValueError("Tobler inputs must be finite")
    if min_speed_kmh <= 0 or max_speed_kmh < min_speed_kmh:
        raise ValueError("Speed bounds must be positive and ordered")
    speed = 6.0 * exp(-3.5 * abs(grade_percent / 100.0 + 0.05))
    return max(min_speed_kmh, min(max_speed_kmh, speed))


def _finish(start: datetime | None, seconds: float | None) -> str | None:
    """Use UTC ISO 8601 only when start and full duration are known."""
    if start is None or seconds is None:
        return None
    try:
        result = start.astimezone(timezone.utc) + timedelta(seconds=seconds)
    except OverflowError as exc:
        raise ForecastError("Forecast finish exceeds datetime range") from exc
    return result.isoformat().replace("+00:00", "Z")


def forecast_activity(
    dataset: AnalyticalDataset,
    *,
    options: ForecastOptions = ForecastOptions(),
) -> ActivityForecastResult:
    """Forecast Tobler moving time with explicit missing-grade policy.

    Rest is a route-wide allowance, never implicitly allocated to segments.
    Checkpoint ETAs require exact, unique original vertex identity and a
    fully forecastable preceding route; independent segments are never joined.
    """
    analyze_route(dataset)  # Enforce F06 identity and measurement contracts.
    groups = {}
    for point in dataset.points:
        if point.kind != "waypoint":
            groups.setdefault(
                (point.kind, point.index, point.segment), []
            ).append(point)
    edges = []
    summaries = []
    diagnostics = []
    timing = {}
    accumulated = 0.0
    route_complete = True
    ordered = []
    for segment in dataset.segments:
        key = (segment.kind, segment.index, segment.segment)
        points = groups.get(key, [])
        if len(points) != segment.point_count:
            raise ForecastError("Analytical segment point count mismatch")
        segment_seconds = 0.0
        covered = 0.0
        complete = True
        previous = None
        for point in points:
            if previous is None:
                timing[(key, point.point)] = (
                    accumulated if route_complete else None
                )
                previous = point
                continue
            length = point.cumulative_distance_m - previous.cumulative_distance_m
            if not isfinite(length) or length < 0:
                raise ForecastError("Invalid segment edge distance")
            grade = point.grade_percent
            assumed = grade is None and options.missing_grade == "assume"
            if grade is None and not assumed and length > 0:
                complete = False
                seconds = speed = None
                diagnostics.append("GRADE_UNAVAILABLE")
            else:
                if length == 0:
                    seconds = 0.0
                    speed = None
                else:
                    effective_grade = (
                        options.assumed_grade_percent if assumed else grade
                    )
                    speed = tobler_speed_kmh(
                        effective_grade,
                        min_speed_kmh=options.min_speed_kmh,
                        max_speed_kmh=options.max_speed_kmh,
                    )
                    seconds = length * 3.6 / speed
                covered += length
                if seconds is not None:
                    segment_seconds += seconds
            edges.append(ForecastEdge(
                segment.kind, segment.index, segment.segment, point.point,
                length, grade, assumed, speed, seconds,
            ))
            if route_complete and seconds is not None:
                accumulated += seconds
                timing[(key, point.point)] = accumulated
            else:
                route_complete = False
                timing[(key, point.point)] = None
            previous = point
        if not complete:
            route_complete = False
        summaries.append(ForecastSegment(
            segment.kind, segment.index, segment.segment, len(points),
            segment.horizontal_distance_m,
            segment_seconds if complete else None, covered, complete,
        ))
        ordered.append((key, points))
    total_moving = sum(s.moving_s for s in summaries) if route_complete else None
    scenarios = []
    for label, factor in (
        ("optimistic", options.optimistic_factor),
        ("nominal", 1.0),
        ("conservative", options.conservative_factor),
    ):
        moving = total_moving * factor if total_moving is not None else None
        elapsed = moving + options.rest_seconds if moving is not None else None
        scenarios.append(ForecastScenario(
            label, moving, options.rest_seconds, elapsed,
            _finish(options.start_time, elapsed),
        ))
    checkpoints = []
    catalog = dataset.waypoint_catalog
    if catalog is not None:
        checkpoint_entries = sorted(
            (w for w in catalog.entries if w.checkpoint_order is not None),
            key=lambda w: w.checkpoint_order,
        )
        last_location = -1
        all_points = [
            (key, point) for key, points in ordered for point in points
        ]
        for checkpoint in checkpoint_entries:
            hits = [
                (position, key, point)
                for position, (key, point) in enumerate(all_points)
                if checkpoint.latitude == point.latitude
                and checkpoint.longitude == point.longitude
            ]
            if len(hits) != 1 or hits[0][0] <= last_location:
                diagnostics.append("CHECKPOINT_POSITION_AMBIGUOUS")
                continue
            position, key, point = hits[0]
            elapsed = timing.get((key, point.point))
            if elapsed is None:
                diagnostics.append("CHECKPOINT_ETA_UNAVAILABLE")
                continue
            checkpoints.append(CheckpointETA(
                checkpoint.index, checkpoint.checkpoint_order,
                key[0], key[1], key[2], point.point,
                elapsed, _finish(options.start_time, elapsed),
            ))
            last_location = position
    else:
        diagnostics.append("CHECKPOINT_CATALOG_UNAVAILABLE")
    if options.start_time is None:
        diagnostics.append("START_TIME_UNAVAILABLE")
    if options.rest_seconds:
        diagnostics.append("REST_NOT_ALLOCATED_TO_CHECKPOINTS")
    if not route_complete:
        diagnostics.append("INCOMPLETE_FORECAST")
    if options.missing_grade == "assume" and any(e.grade_assumed for e in edges):
        diagnostics.append("ASSUMED_GRADE_USED")
    return ActivityForecastResult(
        "1.0.0", dataset.source_sha256, "tobler", "1.0.0",
        dataset.dem_source, dataset.dem_vertical_datum,
        options, tuple(edges), tuple(summaries), tuple(scenarios),
        tuple(checkpoints), tuple(dict.fromkeys(diagnostics)),
    )


def activity_forecast_json(result: ActivityForecastResult) -> bytes:
    """Serialize deterministic JSON without nonfinite quantities."""
    payload = asdict(result)
    payload["options"]["start_time"] = (
        result.options.start_time.isoformat()
        if result.options.start_time is not None else None
    )
    return (json.dumps(payload, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode()
