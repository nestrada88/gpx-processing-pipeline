"""F06 canonical analytical dataset assembled from F01-F05 derived outputs.

Source GPX bytes are immutable. Original coordinates, times and elevations are
never replaced with DEM, terrain, or temporal estimates. Stable segment and
point identifiers prevent incorrect cross-segment joins.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite

from .dem import DEMResult
from .interoperability import GPX11_NAMESPACE, GPXDocument
from .spatial import validate_spatial
from .temporal import analyze_temporal
from .terrain import analyze_terrain
from .waypoints import WaypointCatalog

_NS = f"{{{GPX11_NAMESPACE}}}"


class AnalyticalDatasetError(ValueError):
    """Reject inconsistent upstream data or invalid spatial geometry."""


@dataclass(frozen=True, slots=True)
class AnalyticalPoint:
    """Represent a source point and separately identified derived columns."""

    kind: str
    index: int
    segment: int | None
    point: int
    latitude: float
    longitude: float
    recorded_elevation_text: str | None
    recorded_time_text: str | None
    dem_elevation_m: float | None
    dem_status: str | None
    cumulative_distance_m: float | None
    grade_percent: float | None
    elapsed_from_previous_s: float | None
    observed_speed_m_s: float | None


@dataclass(frozen=True, slots=True)
class AnalyticalSegment:
    """Expose geometry and completeness for one original GPX segment."""

    kind: str
    index: int
    segment: int | None
    point_count: int
    horizontal_distance_m: float
    terrain_complete: bool | None
    timing_complete: bool | None


@dataclass(frozen=True, slots=True)
class AnalyticalDataset:
    """Collect ordered data rows and their calculation lineage."""

    schema_version: str
    source_sha256: str
    points: tuple[AnalyticalPoint, ...]
    segments: tuple[AnalyticalSegment, ...]
    waypoint_catalog: WaypointCatalog | None
    dem_source: str | None
    dem_vertical_datum: str | None
    diagnostics: tuple[str, ...]


def _text(element, name: str) -> str | None:
    """Extract source text losslessly at the XML text-node level."""
    child = element.find(f"{_NS}{name}")
    return None if child is None else child.text


def _source_sequences(root):
    """Enumerate source tracks followed by routes, matching F02 ordering."""
    for index, track in enumerate(root.findall(f"{_NS}trk")):
        for segment_index, segment in enumerate(track.findall(f"{_NS}trkseg")):
            yield "track", index, segment_index, segment.findall(f"{_NS}trkpt")
    for index, route in enumerate(root.findall(f"{_NS}rte")):
        yield "route", index, None, route.findall(f"{_NS}rtept")


def build_analytical_dataset(
    document: GPXDocument,
    *,
    dem: DEMResult | None = None,
    waypoints: WaypointCatalog | None = None,
    include_temporal: bool = True,
) -> AnalyticalDataset:
    """Assemble F01-F05 outputs without changing recorded source measurements.

    DEM and temporal data are optional; absent enrichment is represented by
    null fields rather than fabricated zeroes. Upstream data must match source
    identities or this assembly fails closed.
    """
    spatial = validate_spatial(document)
    if not spatial.valid:
        raise AnalyticalDatasetError("F02 spatial validation failed")
    root = document.tree()
    sequences = list(_source_sequences(root))
    if len(sequences) != len(spatial.distances_m):
        raise AnalyticalDatasetError("Spatial segment count mismatch")

    terrain = analyze_terrain(document, dem) if dem is not None else None
    temporal = analyze_temporal(document) if include_temporal else None
    profile = {
        (segment.kind, segment.index, segment.segment): segment
        for segment in terrain.segments
    } if terrain else {}
    timings = {
        (segment.track, segment.segment): segment
        for segment in temporal.segments
    } if temporal else {}
    samples = {}
    if dem is not None:
        samples = {
            (item.kind, item.index, item.segment, item.point): item
            for item in dem.samples
        }
    if waypoints is not None:
        source_waypoints = root.findall(f"{_NS}wpt")
        if len(waypoints.entries) != len(source_waypoints):
            raise AnalyticalDatasetError("Waypoint catalog count mismatch")
        for index, (entry, element) in enumerate(
            zip(waypoints.entries, source_waypoints)
        ):
            if (
                entry.index != index
                or entry.latitude != float(element.get("lat"))
                or entry.longitude != float(element.get("lon"))
                or entry.name != _text(element, "name")
            ):
                raise AnalyticalDatasetError("Waypoint catalog source mismatch")

    rows = []
    segment_rows = []
    for (kind, index, segment, elements), edges in zip(
        sequences, spatial.distances_m
    ):
        key = kind, index, segment
        analysis = profile.get(key)
        timing = timings.get((index, segment)) if kind == "track" else None
        if len(edges) != max(len(elements) - 1, 0):
            raise AnalyticalDatasetError("Spatial edge count mismatch")
        if analysis and len(analysis.points) != len(elements):
            raise AnalyticalDatasetError("Terrain profile count mismatch")
        if timing and len(timing.edges) != max(len(elements) - 1, 0):
            raise AnalyticalDatasetError("Temporal edge count mismatch")
        distance = 0.0
        for point_index, element in enumerate(elements):
            if point_index:
                distance += edges[point_index - 1]
            lookup = kind, index, segment, point_index
            sample = samples.get(lookup)
            profile_point = analysis.points[point_index] if analysis else None
            edge = timing.edges[point_index - 1] if timing and point_index else None
            rows.append(
                AnalyticalPoint(
                    kind=kind, index=index, segment=segment, point=point_index,
                    latitude=float(element.get("lat")),
                    longitude=float(element.get("lon")),
                    recorded_elevation_text=_text(element, "ele"),
                    recorded_time_text=_text(element, "time"),
                    dem_elevation_m=(
                        sample.elevation_m if sample and sample.status == "ok"
                        else None
                    ),
                    dem_status=sample.status if sample else None,
                    cumulative_distance_m=distance,
                    grade_percent=profile_point.grade_percent if profile_point else None,
                    elapsed_from_previous_s=edge.elapsed_s if edge else None,
                    observed_speed_m_s=edge.speed_m_s if edge else None,
                )
            )
        segment_rows.append(
            AnalyticalSegment(
                kind=kind, index=index, segment=segment,
                point_count=len(elements), horizontal_distance_m=distance,
                terrain_complete=analysis.complete if analysis else None,
                timing_complete=timing.complete if timing else None,
            )
        )

    for index, element in enumerate(root.findall(f"{_NS}wpt")):
        sample = samples.get(("waypoint", index, None, 0))
        rows.append(
            AnalyticalPoint(
                kind="waypoint", index=index, segment=None, point=0,
                latitude=float(element.get("lat")),
                longitude=float(element.get("lon")),
                recorded_elevation_text=_text(element, "ele"),
                recorded_time_text=_text(element, "time"),
                dem_elevation_m=(
                    sample.elevation_m if sample and sample.status == "ok"
                    else None
                ),
                dem_status=sample.status if sample else None,
                cumulative_distance_m=None, grade_percent=None,
                elapsed_from_previous_s=None, observed_speed_m_s=None,
            )
        )
    diagnostics = []
    if dem is None:
        diagnostics.append("DEM_NOT_SUPPLIED")
    if waypoints is None:
        diagnostics.append("WAYPOINT_CATALOG_NOT_SUPPLIED")
    if temporal is None:
        diagnostics.append("TEMPORAL_NOT_COMPUTED")
    else:
        diagnostics.extend(f"temporal:{finding.code}" for finding in temporal.findings)
    if terrain:
        diagnostics.extend(f"terrain:{finding.code}" for finding in terrain.findings)
    if waypoints:
        diagnostics.extend(f"waypoints:{finding.code}" for finding in waypoints.findings)

    return AnalyticalDataset(
        schema_version="1.0.0",
        source_sha256=sha256(document.xml).hexdigest(),
        points=tuple(rows), segments=tuple(segment_rows),
        waypoint_catalog=waypoints,
        dem_source=dem.provenance.source if dem else None,
        dem_vertical_datum=dem.provenance.vertical_datum if dem else None,
        diagnostics=tuple(diagnostics),
    )


def analytical_json(dataset: AnalyticalDataset) -> bytes:
    """Serialize a deterministic UTF-8 JSON analytical product."""
    return (
        json.dumps(
            asdict(dataset), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ) + "\n"
    ).encode("utf-8")
