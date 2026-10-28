# F03 — DEM Enrichment

## Purpose and implementation status

DEM enrichment derives elevations from a local Digital Elevation Model (DEM) for canonical GPX 1.1 points without replacing observations or editing GPX geometry. The implementation is in [`src/gpx_pipeline/dem.py`](../src/gpx_pipeline/dem.py); regression cases are in [`tests/test_f03_dem.py`](../tests/test_f03_dem.py). This document describes the existing implementation, its test evidence, and limitations rather than implying that all historical objectives have been implemented.

This capability consumes F01 `GPXDocument` and requires `validate_spatial(document).valid` from F02. F03 terrain profiles are documented separately in [F03-TERRAIN-ANALYTICS.md](F03-TERRAIN-ANALYTICS.md). Downstream analytical densification and its raster adapter live in `terrain_sampling.py` and `dem_sampling_adapter.py`; they are not changes to canonical F01 geometry.

## Public API

Exported from `gpx_pipeline` and `gpx_pipeline.dem`:

```python
enrich_dem(
    document: GPXDocument,
    raster_path: str | Path,
    *,
    vertical_datum: str | None = None,
    uncertainty_m: float | None = None,
    options: DEMOptions = DEMOptions(),
) -> DEMResult
```

- `DEMOptions(method="nearest", max_raster_bytes=2_000_000_000, max_points=300_000)` is a frozen dataclass. `method` accepts only `nearest` or `bilinear`; both limits must be positive.
- `DEMSample(kind, index, segment, point, elevation_m, status)` identifies one original waypoint, track point, or route point. `kind` is `waypoint`, `track`, or `route`; indexes are zero-based and track `segment` is zero-based (otherwise `None`). Waypoints have point index zero.
- `DEMResult(samples, provenance)` contains an ordered tuple of derived samples and shared `DEMProvenance(source, horizontal_crs, vertical_datum, vertical_units, resolution, method, uncertainty_m)`.
- `DEMError` is the domain-specific `ValueError` subtype for explicitly handled raster/configuration failures. Invalid option or uncertainty values raise `ValueError`; not every possible `pyproj` or malformed-input exception is normalized to `DEMError`.

Samples are traversed in the order **waypoints, tracks/segments/points, routes/points**, preserving original identity fields. `status="ok"` denotes a finite raster result; `status="missing"` denotes out-of-bounds, masked/NoData, nonfinite, or unavailable interpolation neighbors. The internal sampler can return `invalid_transform` for nonfinite transformed coordinates. Do not assume missing subclasses are distinguished by the public result.

## Raster and geodetic contract

- Input is an existing local **single-band** raster opened with rasterio. The raster must expose a CRS and nondegenerate affine transform; its band units must explicitly be one of `m`, `metre`, `meter`, `metres`, or `meters`.
- Nonunit raster scale or nonzero offset is rejected, rather than silently interpreted. Feet or unspecified elevation units are rejected; no unit conversion is performed.
- Source latitude/longitude are interpreted as WGS 84 and transformed with `Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)`; longitude is the first transformation argument. `errcheck=True` is used for the transformation.
- Nearest sampling selects the cell containing the transformed coordinate using the floored raster row/column. Bilinear sampling interpolates at pixel centers (`column + 0.5`, `row + 0.5`) using up to four neighbors; a missing neighbor with nonzero weight makes the result missing, rather than renormalizing weights.
- Raster `resolution` in provenance is the absolute pair of raster coordinate-axis pixel spacings **in the raster CRS units**. Geographic degrees must never be presented as meters. Pixel spacing is not an accuracy estimate.
- `vertical_datum` is caller-supplied descriptive metadata; **no ellipsoidal/orthometric transformation, geoid correction, or datum compatibility verification occurs**. Unknown datum is represented as `None`. Caller-provided `uncertainty_m` must be finite and nonnegative; `None` means unspecified, not zero uncertainty.

## Geometry preservation and lineage

Original point coordinates, ordering, segment boundaries, recorded `<ele>` values and the F01 document are not mutated by `enrich_dem`. DEM estimates exist only in `DEMSample.elevation_m`, never as replacements for recorded elevation. The provenance reports raster path, CRS, declared datum, meter units, raster resolution, interpolation method and optional supplied uncertainty. `DEMProvenance` does **not** currently carry a raster checksum/version, transformation pipeline identity, or propagated confidence interval. `DEMResult` by itself is not a serialized enriched GPX file.

## Usage

The following uses an existing GPX file and a locally prepared, single-band meter-elevation GeoTIFF with suitable coverage and explicit band units:

```python
from pathlib import Path
from gpx_pipeline import DEMOptions, enrich_dem, parse_gpx

document = parse_gpx(Path("route.gpx").read_bytes(), strict=False)
result = enrich_dem(
    document,
    Path("terrain.tif"),
    vertical_datum=None,  # do not claim a datum you cannot establish
    options=DEMOptions(method="bilinear", max_points=300_000),
)
for sample in result.samples:
    print(sample.kind, sample.index, sample.segment, sample.point,
          sample.status, sample.elevation_m)
print(result.provenance)
```

The caller must independently establish the DEM's real vertical reference and fitness for use. The example does not generate or download `terrain.tif`. Using `strict=False` in the example only selects the F01 parser mode; F02 spatial validity is still required by `enrich_dem`.

## Failures, resource limits and test evidence

- Invalid F02 spatial result, missing raster file, oversized raster, too many source points, unsupported band count/CRS/transform/units/scale/offset produce fail-closed behavior, primarily `DEMError`.
- Rasterio read errors and `OSError` inside the raster block are wrapped as `DEMError`. Some coordinate-transform and metadata errors can propagate directly; callers must not assume uniform exception types.
- The configured raster byte and point-count caps **do not guarantee bounded decompressed raster memory, processing time or cache use**. The DEM callback operation limit used by later analytical sampling is a distinct implementation in `dem_sampling_adapter.py`.
- `tests/test_f03_dem.py` includes synthetic raster cases for nearest sampling at cell centers, bilinear interpolation, missing coverage/NoData, masked interpolation neighbors, F02 invalid data, unsupported vertical units, resource caps and GPX observation preservation. These tests exist in the repository; no fresh test execution is asserted by this documentation change.

## Explicit limitations and unresolved requirements

This module handles a single local raster per call; it does not implement tile mosaicking, overlap prioritization, remote acquisition or automatic DEM selection. It does not verify or transform vertical datums; it does not convert non-meter vertical units, propagate uncertainty, or prove source dataset integrity by checksum. Its tests do not exhaustively establish polar/antimeridian cases, all geodetic transformations, memory/decompression worst cases, or full production numerical correctness. DEM sampling is not trail reconstruction or rerouting. Raw terrain metrics, surface gradient, and relief belong to the separate F03 terrain-analysis module.

## Verification reference

Relevant implementation and checks: `src/gpx_pipeline/dem.py`, `tests/test_f03_dem.py`, F02 `src/gpx_pipeline/spatial.py`, and downstream `src/gpx_pipeline/dem_sampling_adapter.py`. A useful repository-wide check in a configured checkout is `python -m pytest -q`; successful execution must be verified independently and is not claimed here.
