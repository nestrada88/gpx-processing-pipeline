# F02 — Spatial Integrity

## Purpose and scope

F02 performs **non-mutating spatial validation and WGS 84 horizontal geodesic
distance calculation** on an F01 `GPXDocument`. It verifies coordinate and
optional elevation numeric validity, reports nonfatal geometric anomalies, and
preserves route, track and segment boundaries. It neither repairs coordinates
nor reconstructs real trails.

**Implementation:** `src/gpx_pipeline/spatial.py`.
**Public exports:** `src/gpx_pipeline/__init__.py`.
**Tests:** `tests/test_f02_spatial.py` and
`tests/integration/test_f01_f03_end_to_end.py`.

## Responsibilities and invariants

- **F02-01 — Coordinate validity:** Latitude must be finite and in the closed
  interval [-90, 90]; longitude must be finite and in [-180, 180], both
  expressed as WGS 84 geographic degrees. Missing and nonnumeric attributes
  are errors. No longitude wrapping, clipping, or repair is performed.
- **F02-02 — Source preservation:** Original coordinate strings, their
  lexical precision, element order and segment grouping remain unchanged.
- **F02-03 — Geometric diagnostics:** Consecutive duplicate positions and
  optionally long displacements produce warnings, not automatic rejection.
  A loop, switchback or self-intersection is not automatically invalid.
- **F02-04 — Segment isolation:** No computed distance joins two distinct GPX
  track segments, tracks, or routes.
- **F02-05 — Geodesy:** Horizontal path distances use the WGS 84 ellipsoid
  through `geographiclib.geodesic.Geodesic.WGS84.Inverse`, in meters.
- **F02-06 — Elevation validity:** The `ele` element may be absent; if
  present, it must contain a finite decimal value. F02 does not interpret
  vertical datum or calculate 3-D distance.
- **F02-07 — Deterministic findings:** Rules and zero-based location indices
  identify where an error or warning arose.
- **F02-08 — No temporal inference:** F02 never estimates movement speed,
  elapsed duration, pace, or ETA.

## Input contract and public Python API

The input to `validate_spatial` is an F01 `GPXDocument`. F02 uses
`document.tree()` to read a detached GPX 1.1 XML tree. GPX 1.1 XSD
validation is an F01/F08 concern; accepting a document into F02 does not
prove prior XSD validation.

| Interface | Implemented contract |
| --- | --- |
| `validate_spatial(document: GPXDocument, *, options: SpatialOptions = SpatialOptions()) -> SpatialResult` | Validate all top-level waypoints and track/route point sequences; calculate within-sequence horizontal edge distances |
| `geodesic_distance_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float` | Return WGS 84 inverse-geodesic distance in meters; invalid coordinate inputs raise `ValueError` |
| `SpatialOptions(jump_warning_m: float \| None = None)` | Optional finite, strictly positive warning threshold in meters; by default no jump threshold applies |
| `SpatialFinding` | Frozen record with `rule`, `severity`, `kind`, `index`, `segment`, `point`, `message` |
| `SpatialResult` | Frozen record with `findings`, `distances_m`, and computed Boolean `valid` property |

`SpatialOptions` rejects zero, negative, NaN and infinite non-null
`jump_warning_m` values with `ValueError`.

## Output contract and ordering

`SpatialResult.findings` is a tuple of `SpatialFinding` records in traversal
order: **waypoints first, then tracks/segments, then routes**. Multiple
findings on one point may occur (for example, invalid coordinates and invalid
elevation).

`SpatialFinding.kind` is `"waypoint"`, `"track"`, or `"route"`.
`index` is zero-based within its corresponding element kind; `segment`
is zero-based for track segments, otherwise `None`; `point` is zero-based
within that waypoint/track segment/route sequence. Waypoint findings use
`point=0` and `index` for the waypoint's index.

`SpatialResult.distances_m` is a tuple of tuples. Arrays appear in this
order: **all track segments (track order, then segment order), followed by
all routes (route order)**. Standalone waypoints contribute no distance array.
Each sequence with `N` points contributes `max(N - 1, 0)` edges; an
empty or singleton segment/route produces `()`.

Every valid edge is a **horizontal geodesic distance in meters**, never a
3-D path distance. If either coordinate endpoint of an edge is invalid, its
distance value is `float("nan")`; no adjacent points are connected across
the invalid endpoint. Consumers **must check `result.valid` before using
the distances**. There is no extra edge spanning neighboring GPX segments.

`SpatialResult.valid` is `True` exactly when no finding has
`severity == "error"`. Warnings do not invalidate the result.

## Implemented diagnostic rules

| Rule | Severity | Trigger |
| --- | --- | --- |
| `SPATIAL_COORDINATE` | error | Latitude/longitude missing, invalid decimal, nonfinite or outside WGS 84 bounds |
| `SPATIAL_ELEVATION` | error | Optional `ele` is present but cannot be interpreted as a finite decimal |
| `SPATIAL_DUPLICATE` | warning | Valid adjacent coordinate positions have zero horizontal distance |
| `SPATIAL_JUMP` | warning | Valid adjacent horizontal distance exceeds `options.jump_warning_m` when configured |

The jump comparison uses **strictly greater than** (`>`). Duplicate
positions produce `SPATIAL_DUPLICATE` and do not also produce a jump
warning. Large displacements are not automatically invalid because they
could be legitimate route geometry or data acquisition artifacts.

F02 does **not** implement a general-purpose discontinuity classifier,
self-intersection detector, positional uncertainty model, or route-point
smoothing. Such behavior must not be inferred from the earlier verification
requirements.

## Usage

```python
from gpx_pipeline import (
    SpatialOptions,
    parse_gpx,
    validate_spatial,
)

source = (
    b'<gpx xmlns="http://www.topografix.com/GPX/1/1" '
    b'version="1.1" creator="example">'
    b'<trk><trkseg>'
    b'<trkpt lat="0" lon="0"/>'
    b'<trkpt lat="0" lon="1"/>'
    b'</trkseg></trk></gpx>'
)
document = parse_gpx(source, strict=False)
result = validate_spatial(
    document,
    options=SpatialOptions(jump_warning_m=200_000),
)
assert result.valid
assert len(result.distances_m) == 1
assert len(result.distances_m[0]) == 1
```

**Boundary of this example:** `parse_gpx(..., strict=False)` checks secure
XML ingestion and the GPX root namespace, not full GPX XSD compliance. Use
F08 production validation where strict structural schema enforcement is
required.

For direct geodesic measurement:

```python
from gpx_pipeline import geodesic_distance_m

meters = geodesic_distance_m(0.0, 0.0, 0.0, 1.0)
assert abs(meters - 111_319.49079327357) < 0.001
```

## Verification evidence

Implemented regression cases in `tests/test_f02_spatial.py` cover:

- WGS 84 coordinate boundaries, invalid latitude/longitude, NaN,
  Infinity and malformed coordinate numbers.
- Antimeridian shortest-arc distance and a numerical reference for one
  equatorial degree (111,319.49079327357 m, tolerance 0.001 m).
- Separate distance arrays for distinct track segments, including a
  singleton segment.
- Invalid intermediate coordinates producing NaN for both adjacent edges.
- Duplicate-coordinate warnings, optional jump warnings, and rejection
  of invalid jump thresholds.
- Optional elevation finiteness checks, byte-for-byte nonmutation and
  repeated-run determinism.
- Direct `geodesic_distance_m` rejection of out-of-range/nonfinite inputs.

The F01–F03 integration tests verify the spatial result participates in
DEM/terrain processing without altering the input GPX snapshot.

**Coverage qualification:** The earlier specification also called for
property-based generation, explicit polar reference cases, multi-route
stress cases and self-intersection/loop fixtures. Those are documented
verification objectives, **not established as implemented tests** by the
F02 test module. Documentation must not claim broader proof than exists.

## Dependencies and excluded concerns

F02 depends on F01's parsed GPX document and the `geographiclib` library.
Downstream F03 and F06 use spatial measurements, but F02 does not:

- Parse untrusted XML or validate GPX/Garmin XSD structure (F01/F08).
- Alter geometry, point counts, precision or segment boundaries.
- Densify, simplify or reconstruct tracks, or resolve actual trail geometry.
- Sample DEM elevations or infer terrain slope and vertical datum (F03).
- Validate timestamps or derive velocity and plausibility (F04).
- Forecast walking time or generate Garmin navigation artifacts (F06/F07).

## Implementation status

**Implemented and merged into `main`.** F02 has an implementation module,
regression tests, and F01–F03 integration coverage. The former
`"implemented only once ..."` completion statement is a historical
requirement, not the current repository status.

## References

- Implementation: `src/gpx_pipeline/spatial.py`
- Public exports: `src/gpx_pipeline/__init__.py`
- Regression tests: `tests/test_f02_spatial.py`
- Integration tests: `tests/integration/test_f01_f03_end_to_end.py`
- F01 documentation: [GPX Interoperability](domains/F01-gpx-interoperability.md)
- Standard: https://www.topografix.com/gpx/1/1/
- Geodesic reference: https://geographiclib.sourceforge.io/
