"""Integrate local F03 DEM rasters with immutable adaptive analytical sampling.

Reuses F03 pixel interpretation and the F06 terrain-adaptive algorithm.
Elevation is sampled in raster-declared metres without vertical conversion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isfinite
from pathlib import Path

import rasterio
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError

from .analytical import AnalyticalDataset
from .dem import DEMError, DEMOptions, DEMProvenance, _sample
from .terrain_sampling import (
    SamplingOptions,
    SamplingResult,
    terrain_adaptive_sample,
)


@dataclass(frozen=True, slots=True)
class DEMSamplingResult:
    """Bind derived analytical samples to the full raster provenance record."""

    schema_version: str
    sampling: SamplingResult
    provenance: DEMProvenance
    sample_operations: int


def sample_terrain_from_dem(
    dataset: AnalyticalDataset,
    raster_path: str | Path,
    *,
    dem_options: DEMOptions = DEMOptions(),
    sampling_options: SamplingOptions = SamplingOptions(),
    vertical_datum: str | None = None,
    uncertainty_m: float | None = None,
) -> DEMSamplingResult:
    """Adapt a validated local DEM to the existing terrain sampling callback.

    The DEM is held open only for this call. All interpolated positions remain
    hypothetical geodesic locations between actual source vertices, never
    reconstructed trail geometry. The raster is not modified.
    """
    if uncertainty_m is not None and (
        not isfinite(uncertainty_m) or uncertainty_m < 0
    ):
        raise ValueError("uncertainty_m must be finite and nonnegative")
    if vertical_datum is not None and (
        not isinstance(vertical_datum, str) or not vertical_datum.strip()
    ):
        raise ValueError("vertical_datum must be nonempty or None")

    path = Path(raster_path)
    if not path.is_file():
        raise DEMError("DEM raster does not exist")
    if path.stat().st_size > dem_options.max_raster_bytes:
        raise DEMError("Raster exceeds configured byte limit")

    operations = 0
    try:
        with rasterio.open(path) as raster:
            if raster.count != 1:
                raise DEMError("Expected a single-band DEM")
            if raster.crs is None:
                raise DEMError("DEM CRS must be defined")
            if raster.transform.is_degenerate:
                raise DEMError("DEM transform is degenerate")
            units = raster.units[0]
            if units not in {"m", "metre", "meter", "metres", "meters"}:
                raise DEMError("DEM elevation units must explicitly be metres")
            if raster.scales[0] != 1 or raster.offsets[0] != 0:
                raise DEMError("Scaled/offset DEM bands are not supported")
            crs = CRS.from_user_input(raster.crs)
            transformer = Transformer.from_crs(
                "EPSG:4326", crs, always_xy=True
            )
            provenance = DEMProvenance(
                source=str(path),
                horizontal_crs=crs.to_string(),
                vertical_datum=vertical_datum,
                vertical_units="m",
                resolution=(abs(raster.res[0]), abs(raster.res[1])),
                method=dem_options.method,
                uncertainty_m=uncertainty_m,
            )

            def sample_elevation(latitude: float, longitude: float) -> float | None:
                """Convert WGS 84 coordinates and reuse F03 raster sampling."""
                nonlocal operations
                operations += 1
                if operations > dem_options.max_points:
                    raise DEMError("DEM sample operation limit exceeded")
                if not all(isfinite(value) for value in (latitude, longitude)):
                    raise DEMError("Nonfinite sample coordinates")
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise DEMError("Sample coordinates outside WGS 84 bounds")
                try:
                    x, y = transformer.transform(
                        longitude, latitude, errcheck=True
                    )
                except ProjError as exc:
                    raise DEMError("DEM coordinate transformation failed") from exc
                value, status = _sample(raster, x, y, dem_options.method)
                return value if status == "ok" else None

            sampling = terrain_adaptive_sample(
                dataset,
                sample_elevation,
                dem_source_description=str(path),
                options=sampling_options,
            )
    except (rasterio.errors.RasterioError, OSError, ProjError) as exc:
        raise DEMError("DEM raster sampling failed") from exc
    return DEMSamplingResult(
        "1.0.0", sampling, provenance, operations
    )


def dem_sampling_json(result: DEMSamplingResult) -> bytes:
    """Serialize deterministic JSON with full DEM and source provenance."""
    return (
        json.dumps(
            asdict(result),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ) + "\n"
    ).encode("utf-8")
