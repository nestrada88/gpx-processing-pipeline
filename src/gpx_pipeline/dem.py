"""Deterministic, non-mutating elevation sampling from a local DEM raster.

Sampling consumes F01's GPXDocument and refuses invalid F02 geometry. DEM
samples and provenance remain separate from recorded GPX elevation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

from .interoperability import GPX11_NAMESPACE, GPXDocument
from .spatial import validate_spatial

_NS = f"{{{GPX11_NAMESPACE}}}"


class DEMError(ValueError):
    """Represent invalid raster configuration or processing errors."""


@dataclass(frozen=True, slots=True)
class DEMOptions:
    """Configure bounded, local raster sampling."""

    method: str = "nearest"
    max_raster_bytes: int = 2_000_000_000
    max_points: int = 300_000

    def __post_init__(self) -> None:
        """Validate interpolation and resource configuration."""
        if self.method not in {"nearest", "bilinear"}:
            raise ValueError("method must be nearest or bilinear")
        if self.max_raster_bytes < 1 or self.max_points < 1:
            raise ValueError("Resource limits must be positive")


@dataclass(frozen=True, slots=True)
class DEMProvenance:
    """Identify source raster and geodetic context of every sample."""

    source: str
    horizontal_crs: str
    vertical_datum: str | None
    vertical_units: str
    resolution: tuple[float, float]
    method: str
    uncertainty_m: float | None


@dataclass(frozen=True, slots=True)
class DEMSample:
    """Represent one input point's DEM-derived elevation or missing value."""

    kind: str
    index: int
    segment: int | None
    point: int
    elevation_m: float | None
    status: str


@dataclass(frozen=True, slots=True)
class DEMResult:
    """Expose ordered derived samples and shared source provenance."""

    samples: tuple[DEMSample, ...]
    provenance: DEMProvenance


def _point_elements(root):
    """Yield GPX waypoints, track points and route points with stable indices."""
    for index, point in enumerate(root.findall(f"{_NS}wpt")):
        yield "waypoint", index, None, 0, point
    for index, track in enumerate(root.findall(f"{_NS}trk")):
        for segment_index, segment in enumerate(track.findall(f"{_NS}trkseg")):
            for point_index, point in enumerate(segment.findall(f"{_NS}trkpt")):
                yield "track", index, segment_index, point_index, point
    for index, route in enumerate(root.findall(f"{_NS}rte")):
        for point_index, point in enumerate(route.findall(f"{_NS}rtept")):
            yield "route", index, None, point_index, point


def _pixel_value(dataset, row: int, col: int) -> float | None:
    """Read a single raster cell, respecting NoData and masks."""
    if not (0 <= row < dataset.height and 0 <= col < dataset.width):
        return None
    value = dataset.read(1, window=Window(col, row, 1, 1), masked=True)
    if np.ma.is_masked(value[0, 0]):
        return None
    scalar = float(value[0, 0])
    return scalar if isfinite(scalar) else None


def _sample(dataset, x: float, y: float, method: str) -> tuple[float | None, str]:
    """Sample a raster with nearest or four-cell bilinear interpolation."""
    if not (isfinite(x) and isfinite(y)):
        return None, "invalid_transform"
    col, row = (~dataset.transform) * (x, y)
    if not (isfinite(col) and isfinite(row)):
        return None, "invalid_transform"

    if method == "nearest":
        # Rasterio's cell selection uses the integer containing cell.
        value = _pixel_value(dataset, floor(row), floor(col))
        return (value, "ok") if value is not None else (None, "missing")

    # Bilinear interpolation is defined with cell centers at (j+.5, i+.5).
    u, v = col - 0.5, row - 0.5
    j, i = floor(u), floor(v)
    dx, dy = u - j, v - i
    weights = (
        ((i, j), (1 - dx) * (1 - dy)),
        ((i, j + 1), dx * (1 - dy)),
        ((i + 1, j), (1 - dx) * dy),
        ((i + 1, j + 1), dx * dy),
    )
    result = 0.0
    for (r, c), weight in weights:
        if weight == 0:
            continue
        value = _pixel_value(dataset, r, c)
        if value is None:
            return None, "missing"
        result += weight * value
    return result, "ok"


def enrich_dem(
    document: GPXDocument,
    raster_path: str | Path,
    *,
    vertical_datum: str | None = None,
    uncertainty_m: float | None = None,
    options: DEMOptions = DEMOptions(),
) -> DEMResult:
    """Attach DEM-derived elevations without modifying source GPX content.

    Samples are in metres only when the raster's band metadata explicitly
    declares metres or the caller independently verifies and sets the units
    through the DEM source. Unsupported units fail closed.
    """
    if uncertainty_m is not None and (
        not isfinite(uncertainty_m) or uncertainty_m < 0
    ):
        raise ValueError("uncertainty_m must be finite and nonnegative")
    spatial = validate_spatial(document)
    if not spatial.valid:
        raise DEMError("F02 spatial validation failed")

    path = Path(raster_path)
    if not path.is_file():
        raise DEMError("DEM raster does not exist")
    if path.stat().st_size > options.max_raster_bytes:
        raise DEMError("Raster exceeds configured byte limit")

    root = document.tree()
    points = list(_point_elements(root))
    if len(points) > options.max_points:
        raise DEMError("GPX exceeds configured sample count")

    try:
        with rasterio.open(path) as dataset:
            if dataset.count != 1:
                raise DEMError("Expected a single-band DEM")
            if dataset.crs is None:
                raise DEMError("DEM CRS must be defined")
            if dataset.transform.is_degenerate:
                raise DEMError("DEM transform is degenerate")
            units = dataset.units[0]
            if units not in {"m", "metre", "meter", "metres", "meters"}:
                raise DEMError("DEM elevation units must explicitly be metres")
            if dataset.scales[0] != 1 or dataset.offsets[0] != 0:
                raise DEMError("Scaled/offset DEM bands are not supported")
            crs = CRS.from_user_input(dataset.crs)
            transform = Transformer.from_crs(
                "EPSG:4326", crs, always_xy=True
            )
            results = []
            for kind, index, segment, point, element in points:
                latitude = float(element.get("lat"))
                longitude = float(element.get("lon"))
                x, y = transform.transform(longitude, latitude, errcheck=True)
                elevation, status = _sample(dataset, x, y, options.method)
                results.append(
                    DEMSample(kind, index, segment, point, elevation, status)
                )
            provenance = DEMProvenance(
                source=str(path),
                horizontal_crs=crs.to_string(),
                vertical_datum=vertical_datum,
                vertical_units="m",
                resolution=(abs(dataset.res[0]), abs(dataset.res[1])),
                method=options.method,
                uncertainty_m=uncertainty_m,
            )
    except (rasterio.errors.RasterioError, OSError) as exc:
        raise DEMError(f"DEM read failed: {exc}") from exc

    return DEMResult(tuple(results), provenance)
