"""Non-mutating spatial validation for canonical F01 GPX documents.

Geodesic lengths use the WGS 84 ellipsoid via GeographicLib. Findings refer to
zero-based track/segment/point indices; route and waypoint indices are separate.
Route points and track points are not joined across GPX element boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite

from geographiclib.geodesic import Geodesic
from lxml import etree

from .interoperability import GPX11_NAMESPACE, GPXDocument

_NS = f"{{{GPX11_NAMESPACE}}}"


@dataclass(frozen=True, slots=True)
class SpatialFinding:
    """Locate a deterministic spatial error or non-fatal anomaly."""

    rule: str
    severity: str
    kind: str
    index: int
    segment: int | None
    point: int
    message: str


@dataclass(frozen=True, slots=True)
class SpatialResult:
    """Contain diagnostics and segment-safe horizontal distances."""

    findings: tuple[SpatialFinding, ...]
    distances_m: tuple[tuple[float, ...], ...]

    @property
    def valid(self) -> bool:
        """Return whether all findings are non-fatal."""
        return not any(item.severity == "error" for item in self.findings)


@dataclass(frozen=True, slots=True)
class SpatialOptions:
    """Specify anomaly thresholds without altering original geometry."""

    jump_warning_m: float | None = None

    def __post_init__(self) -> None:
        """Require strictly positive finite warning thresholds when set."""
        if self.jump_warning_m is not None and (
            not isfinite(self.jump_warning_m) or self.jump_warning_m <= 0
        ):
            raise ValueError("jump_warning_m must be finite and positive")


def geodesic_distance_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Calculate WGS 84 ellipsoidal distance in metres."""
    for latitude, longitude in (
        (latitude_a, longitude_a),
        (latitude_b, longitude_b),
    ):
        if not (
            isfinite(latitude)
            and isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise ValueError("Coordinates must be finite WGS 84 degrees")
    return Geodesic.WGS84.Inverse(
        latitude_a, longitude_a, latitude_b, longitude_b
    )["s12"]


def _coordinate(element: etree._Element) -> tuple[float, float]:
    """Extract valid finite WGS 84 coordinates without rewriting XML."""
    values = []
    for name, lower, upper in (
        ("lat", Decimal("-90"), Decimal("90")),
        ("lon", Decimal("-180"), Decimal("180")),
    ):
        raw = element.get(name)
        if raw is None:
            raise ValueError(f"Missing {name}")
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid {name}") from exc
        if not number.is_finite() or not lower <= number <= upper:
            raise ValueError(f"Invalid {name} range or finiteness")
        values.append(float(number))
    return values[0], values[1]


def _check_elevation(element: etree._Element) -> None:
    """Check optional GPX elevation for valid finite decimal content."""
    elevation = element.find(f"{_NS}ele")
    if elevation is not None:
        try:
            value = Decimal(elevation.text or "")
        except InvalidOperation as exc:
            raise ValueError("Invalid elevation") from exc
        if not value.is_finite():
            raise ValueError("Non-finite elevation")


def _find(
    findings: list[SpatialFinding],
    rule: str,
    severity: str,
    kind: str,
    index: int,
    segment: int | None,
    point: int,
    message: str,
) -> None:
    """Append a finding while maintaining traversal order."""
    findings.append(
        SpatialFinding(rule, severity, kind, index, segment, point, message)
    )


def _evaluate_sequence(
    points: list[etree._Element],
    *,
    kind: str,
    index: int,
    segment: int | None,
    options: SpatialOptions,
    findings: list[SpatialFinding],
) -> tuple[float, ...]:
    """Calculate consecutive distances without crossing invalid edges."""
    distances: list[float] = []
    previous: tuple[float, float] | None = None
    for point_index, element in enumerate(points):
        try:
            position = _coordinate(element)
        except ValueError as exc:
            _find(
                findings, "SPATIAL_COORDINATE", "error", kind, index,
                segment, point_index, str(exc),
            )
            position = None
        try:
            _check_elevation(element)
        except ValueError as exc:
            _find(
                findings, "SPATIAL_ELEVATION", "error", kind, index,
                segment, point_index, str(exc),
            )
        if previous is not None and position is not None:
            distance = geodesic_distance_m(*previous, *position)
            distances.append(distance)
            if distance == 0:
                _find(
                    findings, "SPATIAL_DUPLICATE", "warning", kind, index,
                    segment, point_index, "Repeated horizontal position",
                )
            elif (
                options.jump_warning_m is not None
                and distance > options.jump_warning_m
            ):
                _find(
                    findings, "SPATIAL_JUMP", "warning", kind, index,
                    segment, point_index,
                    f"Consecutive displacement {distance:.3f} m exceeds threshold",
                )
        else:
            # NaN indicates an edge with invalid endpoints, never a measurement.
            if point_index > 0:
                distances.append(float("nan"))
        previous = position
    return tuple(distances)


def validate_spatial(
    document: GPXDocument,
    *,
    options: SpatialOptions = SpatialOptions(),
) -> SpatialResult:
    """Validate F01 GPX geometry without mutating the source document.

    Distance arrays are ordered as track segments followed by GPX routes.
    An edge containing invalid coordinates is represented by NaN and an
    explicit coordinate error; callers must check result.valid before use.
    """
    root = document.tree()
    findings: list[SpatialFinding] = []
    distances: list[tuple[float, ...]] = []

    for waypoint_index, waypoint in enumerate(root.findall(f"{_NS}wpt")):
        _evaluate_sequence(
            [waypoint], kind="waypoint", index=waypoint_index, segment=None,
            options=options, findings=findings,
        )

    for track_index, track in enumerate(root.findall(f"{_NS}trk")):
        for segment_index, segment in enumerate(track.findall(f"{_NS}trkseg")):
            points = segment.findall(f"{_NS}trkpt")
            distances.append(
                _evaluate_sequence(
                    points, kind="track", index=track_index,
                    segment=segment_index, options=options, findings=findings,
                )
            )

    for route_index, route in enumerate(root.findall(f"{_NS}rte")):
        points = route.findall(f"{_NS}rtept")
        distances.append(
            _evaluate_sequence(
                points, kind="route", index=route_index, segment=None,
                options=options, findings=findings,
            )
        )

    return SpatialResult(tuple(findings), tuple(distances))
