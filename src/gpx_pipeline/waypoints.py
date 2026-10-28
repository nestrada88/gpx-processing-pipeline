"""F05 waypoint intelligence: immutable, offline-first catalog enrichment.

Coordinates and labels originate from the F01 GPX source snapshot. Category,
checkpoint order, proximity and optional place labels are derived annotations.
Route proximity is computed against *vertices*, not projected trail segments.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable, Mapping

from .interoperability import GPX11_NAMESPACE, GPXDocument
from .spatial import geodesic_distance_m, validate_spatial

_NS = f"{{{GPX11_NAMESPACE}}}"


class WaypointError(ValueError):
    """Reject invalid waypoint inputs or enrichment configuration."""


@dataclass(frozen=True, slots=True)
class WaypointFinding:
    """Identify missing enrichment or a non-fatal classification ambiguity."""

    code: str
    waypoint: int


@dataclass(frozen=True, slots=True)
class WaypointCatalogEntry:
    """Preserve recorded metadata and separate derived route annotations."""

    index: int
    latitude: float
    longitude: float
    name: str | None
    description: str | None
    symbol: str | None
    recorded_type: str | None
    category: str
    checkpoint_order: int | None
    nearest_vertex_m: float | None
    near_route: bool | None
    place_label: str | None
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WaypointCatalog:
    """Contain deterministic waypoint records and diagnostic findings."""

    entries: tuple[WaypointCatalogEntry, ...]
    findings: tuple[WaypointFinding, ...]


def _content(element, name: str) -> str | None:
    """Get a source text value without changing the original XML."""
    child = element.find(f"{_NS}{name}")
    if child is None or child.text is None:
        return None
    return child.text


def _vertices(root) -> tuple[tuple[float, float], ...]:
    """Return recorded track and route vertices without joining segments."""
    vertices = []
    for track in root.findall(f"{_NS}trk"):
        for segment in track.findall(f"{_NS}trkseg"):
            for point in segment.findall(f"{_NS}trkpt"):
                vertices.append((float(point.get("lat")), float(point.get("lon"))))
    for route in root.findall(f"{_NS}rte"):
        for point in route.findall(f"{_NS}rtept"):
            vertices.append((float(point.get("lat")), float(point.get("lon"))))
    return tuple(vertices)


def enrich_waypoints(
    document: GPXDocument,
    *,
    categories: Mapping[int, str] | None = None,
    checkpoints: Mapping[int, int] | None = None,
    proximity_threshold_m: float = 100.0,
    reverse_geocoder: Callable[[float, float], str | None] | None = None,
) -> WaypointCatalog:
    """Build source-preserving waypoints with explicitly configured semantics.

    Category labels and checkpoint positions use waypoint indices; inferred
    hazard classifications are intentionally prohibited. Optional geocoding
    is caller supplied; failures are reported without losing source content.
    """
    if not isfinite(proximity_threshold_m) or proximity_threshold_m < 0:
        raise ValueError("proximity_threshold_m must be finite and nonnegative")
    if reverse_geocoder is not None and not callable(reverse_geocoder):
        raise TypeError("reverse_geocoder must be callable")

    spatial = validate_spatial(document)
    if not spatial.valid:
        raise WaypointError("F02 spatial validation failed")

    root = document.tree()
    waypoints = root.findall(f"{_NS}wpt")
    category_map = dict(categories or {})
    checkpoint_map = dict(checkpoints or {})
    known = set(range(len(waypoints)))
    if not set(category_map).issubset(known):
        raise WaypointError("Category references an unknown waypoint")
    if not set(checkpoint_map).issubset(known):
        raise WaypointError("Checkpoint references an unknown waypoint")
    for category in category_map.values():
        if not isinstance(category, str) or not category.strip():
            raise WaypointError("Categories must be non-empty strings")
    for order in checkpoint_map.values():
        if type(order) is not int or order < 1:
            raise WaypointError("Checkpoint order must be a positive integer")
    if len(set(checkpoint_map.values())) != len(checkpoint_map):
        raise WaypointError("Checkpoint orders must be unique")

    vertices = _vertices(root)
    entries = []
    findings = []
    for index, element in enumerate(waypoints):
        latitude = float(element.get("lat"))
        longitude = float(element.get("lon"))
        distance = min(
            (geodesic_distance_m(latitude, longitude, *vertex)
             for vertex in vertices),
            default=None,
        )
        if distance is None:
            findings.append(WaypointFinding("NO_ROUTE_VERTICES", index))
        label = None
        if reverse_geocoder is not None:
            try:
                result = reverse_geocoder(latitude, longitude)
                if result is not None and not isinstance(result, str):
                    raise ValueError("Geocoder must return a string or None")
                label = result
            except Exception:
                findings.append(WaypointFinding("GEOCODING_FAILED", index))
        provenance = ["gpx:waypoint"]
        if index in category_map:
            provenance.append("user:classification")
        if index in checkpoint_map:
            provenance.append("user:checkpoint_order")
        if distance is not None:
            provenance.append("derived:wgs84_nearest_vertex")
        if label is not None:
            provenance.append("external:geocoder")
        entries.append(WaypointCatalogEntry(
            index=index,
            latitude=latitude,
            longitude=longitude,
            name=_content(element, "name"),
            description=_content(element, "desc"),
            symbol=_content(element, "sym"),
            recorded_type=_content(element, "type"),
            category=category_map.get(index, "unclassified"),
            checkpoint_order=checkpoint_map.get(index),
            nearest_vertex_m=distance,
            near_route=(distance <= proximity_threshold_m
                        if distance is not None else None),
            place_label=label,
            provenance=tuple(provenance),
        ))
    return WaypointCatalog(tuple(entries), tuple(findings))
