"""Non-mutating route profiles and raster-neighborhood terrain measurements.

All profile heights originate from DEMResult; recorded GPX elevations remain
untouched. Metrics are segment-scoped and never connect independent segments.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, degrees, hypot, isfinite
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS

from .dem import DEMResult
from .interoperability import GPX11_NAMESPACE, GPXDocument
from .spatial import validate_spatial

_NS = f"{{{GPX11_NAMESPACE}}}"


class TerrainError(ValueError):
    """Represent invalid analysis inputs or unsupported terrain geometry."""


@dataclass(frozen=True, slots=True)
class TerrainFinding:
    """Identify a numerical or coverage anomaly at an input point."""

    code: str
    kind: str
    index: int
    segment: int | None
    point: int


@dataclass(frozen=True, slots=True)
class ProfilePoint:
    """Represent DEM elevation and accumulated horizontal route distance."""

    point: int
    distance_m: float
    elevation_m: float | None
    grade_percent: float | None


@dataclass(frozen=True, slots=True)
class TerrainSegment:
    """Hold independent track-segment or GPX-route summary statistics."""

    kind: str
    index: int
    segment: int | None
    points: tuple[ProfilePoint, ...]
    horizontal_distance_m: float
    ascent_m: float
    descent_m: float
    minimum_m: float | None
    maximum_m: float | None
    mean_m: float | None
    coverage_fraction: float
    complete: bool


@dataclass(frozen=True, slots=True)
class TerrainResult:
    """Hold profiles, diagnostics, and DEM lineage."""

    segments: tuple[TerrainSegment, ...]
    findings: tuple[TerrainFinding, ...]
    elevation_source: str
    vertical_datum: str | None


@dataclass(frozen=True, slots=True)
class SurfaceMetrics:
    """Describe the central DEM cell's slope and neighborhood relief."""

    slope_degrees: float | None
    relief_m: float | None
    valid_cells: int
    total_cells: int
    horizontal_crs: str
    window_cells: int


def _sequences(document: GPXDocument):
    """Yield route and track point sets in F02 distance-array ordering."""
    root = document.tree()
    for index, track in enumerate(root.findall(f"{_NS}trk")):
        for seg_idx, segment in enumerate(track.findall(f"{_NS}trkseg")):
            yield "track", index, seg_idx, segment.findall(f"{_NS}trkpt")
    for index, route in enumerate(root.findall(f"{_NS}rte")):
        yield "route", index, None, route.findall(f"{_NS}rtept")


def analyze_terrain(document: GPXDocument, dem: DEMResult) -> TerrainResult:
    """Generate segment-safe profiles using point-identified DEM samples.

    Per-segment raw ascent and descent exclude edges with missing DEM values.
    Partial segment totals are marked incomplete; no interpolation is implied.
    """
    spatial = validate_spatial(document)
    if not spatial.valid:
        raise TerrainError("F02 spatial validation failed")
    if dem.provenance.vertical_units != "m":
        raise TerrainError("DEM elevation units must be metres")
    identities = [
        (sample.kind, sample.index, sample.segment, sample.point)
        for sample in dem.samples
    ]
    if len(identities) != len(set(identities)):
        raise TerrainError("Duplicate DEM sample identifiers")
    samples = {key: sample for key, sample in zip(identities, dem.samples)}
    if any(
        sample.status == "ok"
        and (sample.elevation_m is None or not isfinite(sample.elevation_m))
        for sample in dem.samples
    ):
        raise TerrainError("Invalid finite DEM elevation")
    findings: list[TerrainFinding] = []
    segments: list[TerrainSegment] = []
    sequences = list(_sequences(document))
    if len(sequences) != len(spatial.distances_m):
        raise TerrainError("F02 segment identity mismatch")
    expected = {
        (kind, index, segment, point_index)
        for kind, index, segment, points in sequences
        for point_index in range(len(points))
    }
    expected.update(
        ("waypoint", index, None, 0)
        for index, _ in enumerate(
            document.tree().findall(f"{_NS}wpt")
        )
    )
    if set(samples) != expected:
        raise TerrainError("DEM sample identities do not match GPX points")

    for (kind, index, seg_idx, points), edges in zip(
        sequences, spatial.distances_m
    ):
        if len(edges) != max(0, len(points) - 1):
            raise TerrainError("F02 edge count does not match segment")
        profile: list[ProfilePoint] = []
        valid_heights: list[float] = []
        ascent = descent = distance = 0.0
        valid_edges = 0
        previous_height: float | None = None
        for i in range(len(points)):
            if i:
                edge = edges[i - 1]
                if not isfinite(edge) or edge < 0:
                    raise TerrainError("F02 returned invalid horizontal distance")
                distance += edge
            sample = samples[(kind, index, seg_idx, i)]
            height = (
                sample.elevation_m
                if sample.status == "ok" else None
            )
            if height is not None and not isfinite(height):
                raise TerrainError("Nonfinite elevation sample")
            if height is None:
                findings.append(
                    TerrainFinding("TERRAIN_MISSING_ELEVATION", kind,
                                   index, seg_idx, i)
                )
            else:
                valid_heights.append(height)
            grade = None
            if i and previous_height is not None and height is not None:
                delta = height - previous_height
                ascent += max(delta, 0.0)
                descent += max(-delta, 0.0)
                valid_edges += 1
                if edges[i - 1] > 0:
                    grade = 100.0 * delta / edges[i - 1]
                else:
                    findings.append(
                        TerrainFinding("TERRAIN_ZERO_DISTANCE", kind,
                                       index, seg_idx, i)
                    )
            profile.append(ProfilePoint(i, distance, height, grade))
            previous_height = height
        complete = valid_edges == max(0, len(points) - 1) and (
            len(valid_heights) == len(points)
        )
        count = len(valid_heights)
        segments.append(
            TerrainSegment(
                kind, index, seg_idx, tuple(profile), distance, ascent,
                descent, min(valid_heights) if count else None,
                max(valid_heights) if count else None,
                sum(valid_heights) / count if count else None,
                count / len(points) if points else 0.0, complete,
            )
        )
    return TerrainResult(
        tuple(segments), tuple(findings), dem.provenance.source,
        dem.provenance.vertical_datum,
    )


def analyze_dem_surface(
    raster_path: str | Path, row: int, col: int, *, window_cells: int = 3
) -> SurfaceMetrics:
    """Compute central slope and full-neighborhood relief on a metric raster.

    Slope uses 3-by-3 Horn derivatives. Relief uses the configured odd window
    of >=3 cells; any missing window cell makes relief undefined. The raster
    must have orthogonal, metre-based projected axes and metre elevations.
    """
    if window_cells < 3 or window_cells % 2 == 0:
        raise ValueError("window_cells must be odd and >= 3")
    with rasterio.open(raster_path) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise TerrainError("Single-band DEM and CRS required")
        crs = CRS.from_user_input(dataset.crs)
        if not crs.is_projected or any(
            abs(axis.unit_conversion_factor - 1.0) > 1e-9
            for axis in crs.axis_info[:2]
        ):
            raise TerrainError("Projected CRS with metre horizontal axes required")
        affine = dataset.transform
        if affine.b != 0 or affine.d != 0 or affine.a == 0 or affine.e == 0:
            raise TerrainError("Orthogonal nondegenerate raster required")
        if dataset.units[0] not in {
            "m", "metre", "meter", "metres", "meters"
        }:
            raise TerrainError("Metre elevation band units required")
        radius = window_cells // 2
        if not (
            radius <= row < dataset.height - radius
            and radius <= col < dataset.width - radius
        ):
            raise TerrainError("Neighborhood exceeds raster bounds")
        from rasterio.windows import Window

        data = dataset.read(
            1, window=Window(col-radius, row-radius,
                             window_cells, window_cells), masked=True
        )
        values = np.ma.filled(data.astype(float), np.nan)
        valid = np.isfinite(values)
        total = window_cells * window_cells
        relief = (
            float(np.max(values) - np.min(values))
            if valid.all() else None
        )
        center = values[radius-1:radius+2, radius-1:radius+2]
        slope = None
        if np.isfinite(center).all():
            a, b, c = center[0]
            d, _, f = center[1]
            g, h, i = center[2]
            dx, dy = abs(affine.a), abs(affine.e)
            dzdx = ((c + 2*f + i) - (a + 2*d + g)) / (8*dx)
            dzdy = ((g + 2*h + i) - (a + 2*b + c)) / (8*dy)
            slope = degrees(atan(hypot(dzdx, dzdy)))
        return SurfaceMetrics(
            slope, relief, int(valid.sum()), total,
            crs.to_string(), window_cells,
        )
