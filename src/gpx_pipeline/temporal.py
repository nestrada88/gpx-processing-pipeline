"""Deterministic recorded-track temporal validation and kinematic analysis.

F04 consumes F01 source snapshots and F02 segment-scoped geodesic edges.
Recorded timestamps are never modified; no timestamps or speeds are simulated.
Unknown timing and implausible measurements are represented explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
import re

from .interoperability import GPX11_NAMESPACE, GPXDocument
from .spatial import validate_spatial

_NS = f"{{{GPX11_NAMESPACE}}}"
_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class TemporalError(ValueError):
    """Represent invalid processing configuration or upstream geometry."""


@dataclass(frozen=True, slots=True)
class TemporalOptions:
    """Define movement thresholds without asserting universal human limits."""

    speed_warning_m_s: float = 12.0
    moving_speed_m_s: float = 0.5
    gap_warning_s: float = 1800.0

    def __post_init__(self) -> None:
        """Reject invalid or ambiguous thresholds."""
        for value in (
            self.speed_warning_m_s,
            self.moving_speed_m_s,
            self.gap_warning_s,
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError("Temporal thresholds must be finite and positive")


@dataclass(frozen=True, slots=True)
class TemporalFinding:
    """Identify temporal invalidity or a non-fatal movement anomaly."""

    code: str
    severity: str
    track: int
    segment: int
    point: int


@dataclass(frozen=True, slots=True)
class MovementEdge:
    """Describe one original adjacent trackpoint pair."""

    end_point: int
    elapsed_s: float | None
    distance_m: float
    speed_m_s: float | None
    pace_s_km: float | None
    moving: bool | None


@dataclass(frozen=True, slots=True)
class TemporalSegment:
    """Report statistics within one track segment only."""

    track: int
    segment: int
    edges: tuple[MovementEdge, ...]
    elapsed_s: float | None
    moving_s: float
    timed_distance_m: float
    moving_distance_m: float
    average_speed_m_s: float | None
    moving_speed_m_s: float | None
    complete: bool


@dataclass(frozen=True, slots=True)
class TemporalResult:
    """Contain stable diagnostics and recorded-only motion measurements."""

    segments: tuple[TemporalSegment, ...]
    findings: tuple[TemporalFinding, ...]

    @property
    def valid(self) -> bool:
        """Determine whether any fatal chronological errors occurred."""
        return not any(f.severity == "error" for f in self.findings)


def _timestamp(element) -> datetime | None:
    """Parse an explicit GPX timezone offset into an aware UTC timestamp."""
    child = element.find(f"{_NS}time")
    if child is None:
        return None
    text = (child.text or "").strip()
    if not _TIME_PATTERN.fullmatch(text):
        raise ValueError("A complete ISO 8601 timestamp with offset is required")
    try:
        instant = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if instant.utcoffset() is None:
        raise ValueError("Timestamp is missing timezone")
    return instant.astimezone(timezone.utc)


def _segments(document: GPXDocument):
    """Traverse original tracks preserving track and segment indices."""
    root = document.tree()
    for track_index, track in enumerate(root.findall(f"{_NS}trk")):
        for segment_index, segment in enumerate(track.findall(f"{_NS}trkseg")):
            yield track_index, segment_index, segment.findall(f"{_NS}trkpt")


def analyze_temporal(
    document: GPXDocument,
    *,
    options: TemporalOptions = TemporalOptions(),
) -> TemporalResult:
    """Analyze recorded trackpoint chronology without inventing time data.

    Negative or duplicate timestamps are errors. Missing or malformed times
    are errors with undefined adjacent edge calculations. Threshold exceedance
    is a warning and never silently adjusts original observations.
    """
    spatial = validate_spatial(document)
    if not spatial.valid:
        raise TemporalError("F02 spatial validation failed")
    findings: list[TemporalFinding] = []
    summaries: list[TemporalSegment] = []
    tracks = list(_segments(document))
    if len(tracks) > len(spatial.distances_m):
        raise TemporalError("F02 segment count mismatch")
    for sequence_index, (track, segment, points) in enumerate(tracks):
        distances = spatial.distances_m[sequence_index]
        if len(distances) != max(0, len(points) - 1):
            raise TemporalError("F02 distance array mismatch")
        timestamps: list[datetime | None] = []
        for index, element in enumerate(points):
            try:
                instant = _timestamp(element)
            except (ValueError, OverflowError):
                findings.append(
                    TemporalFinding("INVALID_TIMESTAMP", "error", track, segment, index)
                )
                instant = None
            if instant is None and element.find(f"{_NS}time") is None:
                findings.append(
                    TemporalFinding("MISSING_TIMESTAMP", "warning", track, segment, index)
                )
            timestamps.append(instant)
        edges: list[MovementEdge] = []
        moving_seconds = timed_seconds = 0.0
        timed_distance = moving_distance = 0.0
        valid_edges = 0
        for end_index, distance in enumerate(distances, start=1):
            start, finish = timestamps[end_index - 1:end_index + 1]
            if not isfinite(distance) or distance < 0:
                raise TemporalError("F02 returned invalid geodesic distance")
            if start is None or finish is None:
                findings.append(
                    TemporalFinding("UNKNOWN_EDGE_TIME", "warning", track, segment,
                                    end_index)
                )
                edges.append(
                    MovementEdge(end_index, None, distance, None, None, None)
                )
                continue
            elapsed = (finish - start).total_seconds()
            if elapsed <= 0:
                findings.append(
                    TemporalFinding(
                        "DUPLICATE_TIMESTAMP" if elapsed == 0 else
                        "REVERSED_TIMESTAMP",
                        "error", track, segment, end_index,
                    )
                )
                edges.append(
                    MovementEdge(end_index, elapsed, distance, None, None, None)
                )
                continue
            valid_edges += 1
            speed = distance / elapsed
            pace = 1000.0 / speed if speed > 0 else None
            moving = speed >= options.moving_speed_m_s
            timed_seconds += elapsed
            timed_distance += distance
            if moving:
                moving_seconds += elapsed
                moving_distance += distance
            if speed > options.speed_warning_m_s:
                findings.append(
                    TemporalFinding("SPEED_ANOMALY", "warning", track, segment,
                                    end_index)
                )
            if elapsed > options.gap_warning_s:
                findings.append(
                    TemporalFinding("TEMPORAL_GAP", "warning", track, segment,
                                    end_index)
                )
            edges.append(
                MovementEdge(end_index, elapsed, distance, speed, pace, moving)
            )
        complete = (
            all(t is not None for t in timestamps)
            and valid_edges == len(distances)
        )
        # Elapsed duration is known only with complete, strictly ordered timing.
        elapsed_total = timed_seconds if complete else None
        summaries.append(
            TemporalSegment(
                track, segment, tuple(edges), elapsed_total,
                moving_seconds, timed_distance, moving_distance,
                timed_distance / timed_seconds if timed_seconds else None,
                moving_distance / moving_seconds if moving_seconds else None,
                complete,
            )
        )
    return TemporalResult(tuple(summaries), tuple(findings))
