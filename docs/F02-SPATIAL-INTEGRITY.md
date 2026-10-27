# F02 — Spatial Integrity

## Purpose

Validate the spatial integrity of canonical GPX data emitted by F01 without changing source geometry. F02 supplies coordinate validation, segment-safe geometry diagnostics, and geodetic distance primitives for downstream domains.

## Responsibilities

- **F02-01 — Coordinate validation:** enforce latitude in [-90, 90], longitude in [-180, 180], and finite coordinates under WGS 84 geographic coordinates.
- **F02-02 — Precision preservation:** retain canonical source coordinate values without rounding or truncation.
- **F02-03 — Geometric integrity:** identify exact duplicate points, suspicious jumps, and discontinuities while keeping legitimate loops, switchbacks, and self-intersections valid.
- **F02-04 — Segment integrity:** preserve track/segment structure and ordered point sequences; never create an implied edge between distinct segments.
- **F02-05 — Geodesy:** calculate geodesic distances with an explicitly identified Earth model; cover antimeridian crossings and polar coordinates.
- **F02-06 — Spatial diagnostics:** classify and locate anomalous displacements without inferring movement speed from spatial data alone.
- **F02-07 — Source preservation:** guarantee validation is non-mutating.
- **F02-08 — Deterministic findings:** identify track, segment, point, rule, severity, and relevant measurements consistently.

## Contracts

1. Consume the canonical F01 representation. Do not add a parallel GPX parser or competing data model.
2. Invalid coordinates are errors. Coordinate numeric values must be finite; no automatic longitude wrapping or coordinate repair.
3. Missing elevation is permitted; when present it must be finite. Do not assume a GPX elevation is DEM-derived or in a known vertical datum without metadata.
4. Repeated positions, self-intersections, loops, and significant point-to-point distances are not necessarily invalid. Emit configurable diagnostics where appropriate; do not silently discard route geometry.
5. A segment break is never interpreted as a traveled edge. Geodesic distances must not bridge segments by default.
6. Evaluation must not modify point count, point order, coordinate values, track grouping, or segment grouping.
7. Distinguish geodesic horizontal distance from 3-D distance involving elevations, and do not combine unknown vertical datums.
8. Findings must have stable rule identifiers and enough location context to reproduce the issue.

## Excluded concerns

- XML parsing and XSD checks (F01)
- Densification, simplification, smoothing, or route reconstruction
- DEM acquisition, terrain interpolation, and slope estimates
- Chronology, speed, pacing, or ETA modeling
- Garmin device export and navigation behavior

## Verification battery

- Boundary and just-outside-boundary coordinates, finite/nonfinite values, absent elevations.
- Coordinate precision and immutable geometry snapshots before/after validation.
- Dateline crossings, same-position points, polar positions, closed loops, switchbacks, and self-intersections.
- Multiple tracks and segments, including singleton and empty segments where permitted by the upstream canonical contract.
- No implicit cross-segment distance, deterministic ordering of diagnostics, and repeated-run consistency.
- Numerical comparison of geodesic distance against independent, identified reference cases.
- Data-driven and property-based test generation for valid coordinates and invalid perturbations.

## Completion evidence

F02 is implemented only once the listed responsibilities are present in code, integrated with F01, and supported by passing automated tests. This document establishes the working scope; it does not certify implementation or verification.
