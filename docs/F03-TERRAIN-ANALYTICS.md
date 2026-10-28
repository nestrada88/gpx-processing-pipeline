# F03 — Terrain Analytics

## Purpose and implementation status

Terrain analytics calculates DEM-derived elevation profiles and route measurements over immutable, spatially validated GPX geometry. It also provides a separate raster-neighborhood surface-slope and relief calculation. Current code: [`src/gpx_pipeline/terrain.py`](../src/gpx_pipeline/terrain.py). Numerical and integration test cases: [`tests/test_f03_terrain.py`](../tests/test_f03_terrain.py). This document describes actual code behavior, with explicit gaps relative to earlier feature objectives.

F01 provides `GPXDocument`; F02 provides spatial validation and geodesic edge distances; [DEM enrichment](F03-DEM-ENRICHMENT.md) provides point-identified sampled elevations. Neither F03 function modifies GPX observations, vertex locations, or segment boundaries.

## Public APIs and result semantics

```python
analyze_terrain(document: GPXDocument, dem: DEMResult) -> TerrainResult

analyze_dem_surface(
    raster_path: str | Path,
    row: int,
    col: int,
    *,
    window_cells: int = 3,
) -> SurfaceMetrics
```

These functions, `TerrainError`, `TerrainFinding`, `ProfilePoint`, `TerrainSegment`, `TerrainResult` and `SurfaceMetrics` are exported from `gpx_pipeline` and `gpx_pipeline.terrain`.

- `TerrainResult.segments` is a tuple of per-track-segment and per-GPX-route summaries; ordinary standalone waypoints are validated for identity but do not produce route profiles. `findings` contains point-identified diagnostic records; `elevation_source` is the DEM provenance source string and `vertical_datum` is the supplied DEM datum metadata.
- `ProfilePoint(point, distance_m, elevation_m, grade_percent)`: `distance_m` is cumulative distance within the segment, starting at zero; `grade_percent` is undefined (`None`) for the first point and for invalid/zero-distance edges.
- `TerrainSegment` contains `kind`, `index`, `segment`, `points`, `horizontal_distance_m`, raw `ascent_m` and `descent_m`, `minimum_m`, `maximum_m`, `mean_m`, `coverage_fraction`, and `complete`. Minimum/maximum/mean are over available valid elevations, not inferred missing samples.
- `TerrainFinding` carries `code`, `kind`, `index`, `segment`, and `point`; currently emitted codes include `TERRAIN_MISSING_ELEVATION` and `TERRAIN_ZERO_DISTANCE`.
- `SurfaceMetrics` contains `slope_degrees`, `relief_m`, `valid_cells`, `total_cells`, `horizontal_crs`, and `window_cells`. A missing required sample makes the affected metric `None`.

## Identity and input checks

`analyze_terrain` requires an F02-valid source, a DEM result with `provenance.vertical_units == "m"`, and a one-to-one match of unique `(kind, index, segment, point)` identifiers against all source waypoints, track points and route points. Duplicate, missing or extra IDs are rejected. An `ok` sample must have a finite elevation. F02 distance-array count and edge counts must match route/track sequences; invalid distances fail closed with `TerrainError`.

Only **DEM-derived** heights are selected. The implementation does not expose a switch for recorded GPX elevations. A declared vertical datum is passed through as metadata, not independently established or converted.

## Numerical definitions and segment boundaries

For consecutive points `i-1` and `i` in the **same** segment with valid finite DEM heights `h` and valid F02 geodesic horizontal edge distance `d` in meters:

- Route grade in percent is `100 * (h[i] - h[i-1]) / d` when `d > 0`; otherwise it is undefined and `TERRAIN_ZERO_DISTANCE` is reported.
- Raw ascent adds `max(h[i]-h[i-1], 0)`; raw descent adds `max(h[i-1]-h[i], 0)`. These two raw accumulators operate on valid adjacent heights. **In the current implementation a zero-length edge with valid heights can still contribute raw ascent/descent even though its grade is undefined**; this is documented behavior, not a claim that it is physically appropriate.
- Horizontal cumulative distance adds every valid F02 edge independently of DEM coverage. There are no synthetic edges between tracks, segments or routes.
- When a height is unavailable, no adjacent ascent/descent bridge is constructed; the corresponding grade is `None`. `coverage_fraction` is valid height count divided by segment point count, or zero for an empty segment.
- `complete` requires all points to have valid heights and all expected consecutive edges to have two valid heights. For singleton and empty segments the flag follows that exact rule; in particular an empty segment can be marked complete despite coverage fraction zero. Interpret it together with point count and coverage.
- `minimum_m`, `maximum_m`, `mean_m` are calculated on valid DEM samples. `None` represents unavailable statistics. `ascent_m=0` or `descent_m=0` for an incomplete segment **is not evidence of complete-route zero gain/loss**.

### Longitudinal grade versus terrain slope

Route grade uses a one-dimensional height difference along the route. Surface slope uses the two-dimensional elevation gradient around a raster cell; the two metrics must not be conflated.

`analyze_dem_surface` accepts only a single-band DEM with projected CRS whose first two axes use meters, an orthogonal nondegenerate affine raster transform (no rotation/shear), and explicit meter-valued elevation units. `row` and `col` address the center cell, with a fully in-bounds odd `window_cells >= 3` neighborhood.

- Terrain slope uses the central 3×3 neighborhood and Horn finite differences, with `dx=abs(transform.a)`, `dy=abs(transform.e)`. If both horizontal derivatives are `p` and `q`, `slope_degrees = degrees(atan(sqrt(p*p + q*q)))`.
- Relief is maximum minus minimum elevation over the **entire configured** neighborhood, only if all its cells are finite and unmasked. A masked cell outside the central 3×3 may leave slope defined while relief becomes `None`.
- The returned valid/total cell counts describe the full requested window. Unsupported CRS, bands, units, affine geometry, or out-of-bounds windows fail closed; an invalid even or too-small window raises `ValueError`.
- Surface slope is reported in **degrees**, not radians. Unlike `enrich_dem`, this function reads a raster without using the `DEMOptions` raster-file-size cap.

## Reproducible usage

Given an existing GPX input and a local, suitable, single-band meter-elevation GeoTIFF:

```python
from pathlib import Path
from gpx_pipeline import (
    DEMOptions, enrich_dem, analyze_terrain, analyze_dem_surface, parse_gpx
)

document = parse_gpx(Path("route.gpx").read_bytes(), strict=False)
dem = enrich_dem(document, "terrain.tif", options=DEMOptions(method="nearest"))
result = analyze_terrain(document, dem)

for segment in result.segments:
    print(segment.kind, segment.index, segment.segment,
          segment.horizontal_distance_m, segment.ascent_m,
          segment.descent_m, segment.coverage_fraction, segment.complete)
for finding in result.findings:
    print(finding.code, finding.kind, finding.index, finding.segment, finding.point)

# Only for a separate DEM known to have a projected metre-based orthogonal grid:
surface = analyze_dem_surface("metric-terrain.tif", row=10, col=10)
print(surface.slope_degrees, surface.relief_m)
```

The two TIFF paths above are caller-provided data, not bundled assets. A geographic raster accepted by `enrich_dem` may be **rejected** by `analyze_dem_surface`. The example does not perform vertical-datum verification or prove its DEM scientifically appropriate.

## Verification and limitations

The synthetic tests in `tests/test_f03_terrain.py` cover flat/uphill/downhill/oscillating profiles, F02 geodesic reference distances, missing elevation gaps, track-segment isolation, sample-identity mismatches, source immutability, 45-degree planar raster slope, constant-surface relief, NoData and invalid windows. Presence of test files is not evidence of a fresh successful test run; run `python -m pytest -q` in a configured checkout and inspect CI evidence separately.

Remaining limitations: profile source selection is DEM-only; there is no configurable smoothing/filtering of ascent/descent, elevation uncertainty propagation, full independent numerical/property-based verification, or automatic vertical datum compatibility transformation. Surface analysis requires a projected metric orthogonal raster; geographic-grid and rotated-affine slopes are not calculated. Raw elevation data are not a substitute for real trail geometry. Follow-on F06 terrain-adaptive analytical densification is a distinct operation: it interpolates derived analytical points without modifying canonical source points and cannot reconstruct missing path bends.

## Related references

- `docs/F03-DEM-ENRICHMENT.md`, `src/gpx_pipeline/dem.py`
- `src/gpx_pipeline/spatial.py` and `docs/F02-SPATIAL-INTEGRITY.md`
- `src/gpx_pipeline/terrain_sampling.py`, `src/gpx_pipeline/dem_sampling_adapter.py`
- `tests/test_f03_dem.py`, `tests/test_f03_terrain.py`
