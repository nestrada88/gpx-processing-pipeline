# F03 — Terrain Analytics

## Purpose

Derive reproducible terrain metrics from validated route geometry and DEM-enriched elevations without altering source GPX geometry or recorded measurements.

## Dependency and boundary

- Consume F01 canonical route data, F02 spatial/geodesic validation, and the F03 DEM Enrichment data contract.
- Do not implement GPX parsing, coordinate repair, DEM acquisition or elevation sampling, densification, temporal modeling, pacing, or Garmin export.
- Calculate derived values in an analytical layer, not in-place modifications of GPX observations.
- Implementation and verification are separate from this specification.

## Responsibilities

| ID | Capability |
| --- | --- |
| F03-TA-01 | Ordered elevation profile with cumulative in-segment distance |
| F03-TA-02 | Local longitudinal grade as 100 × elevation difference / horizontal geodesic distance |
| F03-TA-03 | Cumulative positive elevation change (ascent) |
| F03-TA-04 | Cumulative negative elevation change (descent) |
| F03-TA-05 | Minimum, maximum, mean and range for valid, selected elevation samples |
| F03-TA-06 | Local terrain slope estimated from spatial DEM neighborhoods |
| F03-TA-07 | Terrain relief on explicitly defined DEM neighborhoods |
| F03-TA-08 | Missing, invalid, or uncertain data diagnostics |
| F03-TA-09 | Deterministic and numerically verified computation |
| F03-TA-10 | Provenance for each metric and its underlying elevation source |

## Mathematical definitions

For adjacent points i and i+1 within the same track segment with valid compatible elevations h_i and h_(i+1), let d_i be the F02 geodesic horizontal distance in meters.

- **Grade (%):** g_i = 100 × (h_(i+1) − h_i) / d_i, defined only when d_i > 0.
- **Raw ascent (m):** sum of max(h_(i+1) − h_i, 0) over valid in-segment adjacent pairs.
- **Raw descent (m):** sum of max(h_i − h_(i+1), 0) over the same pairs.
- **Elevation range (m):** max(valid h) − min(valid h), with explicit behavior for empty input.
- **Terrain slope (radians):** atan(sqrt((dz/dx)^2 + (dz/dy)^2)), where x and y are physical horizontal lengths, not unconverted geographic degrees.
- **Local relief (m):** max(h in neighborhood N) − min(h in N), with N's extent, sample support and resolution included in metadata.

Do not treat longitudinal route grade as equivalent to DEM terrain slope.

## Input and data semantics

1. Elevations may be observed or sampled; select the source explicitly. Never mix unknown or incompatible vertical datums within a computed metric.
2. Preserve every source coordinate, recorded elevation, track/segment boundary and original point order.
3. Never form a distance, grade or ascent/descent edge across track segments or missing elevation samples.
4. Zero-length horizontal edges yield undefined grade and a stable diagnostic, not NaN or infinity in serialized results.
5. Identify raw ascent/descent separately from optional filtered statistics. If filtering is offered, parameterize it and preserve the unfiltered values.
6. Raster terrain gradients require neighborhood DEM access, valid georeferencing, unit conversions, and a documented finite-difference/derivative method. A 1-D route profile alone cannot determine the full 2-D terrain gradient.
7. Report coverage and completeness; a partial sum must not be silently described as a complete-route total.
8. Unknown uncertainty stays unknown. Do not interpret pixel size as accuracy or silently replace recorded elevation.
9. Ensure deterministic sample selection, algorithms, diagnostics and aggregation ordering.

## Verification battery

- Flat, constant-gradient uphill/downhill, alternating-elevation and analytical-surface cases with known expectations.
- Duplicate coordinates and zero-length edges, singleton/empty segments, and split tracks.
- Missing/invalid elevations and NoData neighborhoods, with coverage and completeness diagnostics.
- Recorded vs DEM-derived source choice, vertical units and incompatible vertical datums.
- Noisy DEM profile: raw versus configurable filtered ascent/descent.
- Terrain slope on planes with known partial derivatives, geographic CRS with correct physical units, and edge/nodata handling.
- Relief for constant and varying synthetic neighborhoods, including resolution and window metadata.
- Independent numerical reference tests, repeatability and property-based generated inputs.
- Exact source geometry and recorded elevation preservation.
- F01/F02/DEM enrichment integration tests and explicit behavior when upstream capabilities are not implemented.

## Completion evidence

Completion requires working Python functionality, integration against actual upstream contracts, passing tests covering the verification battery, and demonstrable non-mutation of input geometry. Merging this specification alone does not establish functional completion.
