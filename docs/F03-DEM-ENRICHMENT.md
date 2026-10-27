# F03 — DEM Enrichment

## Purpose

Provide terrain-aware elevation enrichment for F01 canonical GPX data that has passed F02 spatial integrity validation. The analytical master must preserve observed route geometry and recorded measurements while attaching distinct, reproducible DEM-derived information.

## Scope — feat/dem-enrichment

1. **DEM raster access:** local, explicitly configured terrain data sources; deterministic selection and handling of tiles, coverage gaps, and overlaps. External downloads are not required for processing.
2. **Coordinate reference systems:** read DEM CRS metadata; transform WGS 84 GPX horizontal coordinates into the raster sampling CRS using an explicit, tested coordinate operation. Treat axis order as explicit.
3. **Vertical reference:** record the DEM vertical datum and units; do not silently equate orthometric heights, ellipsoidal heights, or unspecified vertical references. Any vertical transformations require documented source/target datums, transformation grids where necessary, and error handling when unavailable.
4. **Elevation sampling:** sample the source DEM at validated coordinates; define nearest-neighbor and bilinear interpolation policies with correct pixel-center conventions, edge handling, and NoData masking.
5. **Missing data:** distinguish outside coverage, NoData, invalid rasters, unavailable transforms, and other processing failures; do not fabricate elevations.
6. **Output data separation:** preserve original point coordinates and recorded elevation as immutable source fields; store sampled DEM elevation separately, together with quality flags and lineage.
7. **Provenance:** record source dataset identifier, resolution, horizontal CRS, vertical datum, units, sampling/interpolation method, data version or checksum when available, and transformation description.
8. **Uncertainty:** report source uncertainty when documented; otherwise mark uncertainty unknown rather than inventing numerical accuracy. Do not conflate DEM pixel spacing with vertical accuracy.
9. **Determinism and resources:** fixed input raster, coordinates, configuration, and software environment yield repeatable results; bound raster access, file size, cache, and memory consumption.

## Invariants

- Original point count, coordinates, ordering, tracks, and segment boundaries do not change.
- Recorded elevation is not replaced by the DEM estimate.
- Interpolating a DEM does not recover sub-sample trail geometry.
- Raster georeferencing and axis order are honored; geographic degree spacing is not interpreted as metric spatial resolution.
- Horizontal and vertical reference systems are tracked independently.
- Invalid or unavailable samples yield explicit diagnostics and missing analytical values.

## Out of scope

- F01 GPX parsing and schema validation.
- F02 spatial coordinate and geodesic validation.
- Track geometry densification, interpolation of the walked trail, or automatic re-routing.
- Longitudinal grade, ascent/descent, terrain slope, relief statistics, and terrain-analytics reports (separate subsequent branch).
- Temporal modeling, pace estimation, or Garmin device output.

## Verification requirements

- DEM sampling over known synthetic rasters with predictable pixel values.
- Pixel-center sampling, edge cells, NoData and partially masked interpolation neighborhoods.
- Geographic and projected rasters; nontrivial CRS transformations and axis-order checks.
- Antimeridian/polar edge behavior only where raster CRS and coverage support those coordinates.
- Vertical unit conversion, explicit datum mismatches, and unavailable vertical transformations.
- Adjacent tiles and overlapping data selection with stable tie-breaking.
- Source-geometry immutability and recorded-vs-derived elevation separation.
- Provenance completeness, stable diagnostics, reproducible results, and bounded resource behavior.
- Controlled missing coverage, corrupt files, and unsupported raster metadata.

## Integration and completion

Consume the F01 canonical representation after F02 validation. Implement domain code and automated tests on this branch before treating the feature as operational. This file is a technical specification, not evidence that DEM enrichment has been implemented or verified.
