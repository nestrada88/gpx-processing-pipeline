# F05 — Waypoint Intelligence

## Purpose and implementation status

F05 builds a deterministic, source-preserving catalog of GPX 1.1 **standalone waypoints** (`<wpt>`), combining recorded labels with optional user classifications, checkpoint positions, nearest recorded route/track **vertex** proximity and caller-supplied place labels. The implementation is in [`src/gpx_pipeline/waypoints.py`](../src/gpx_pipeline/waypoints.py), with regression cases in [`tests/test_f05_waypoints.py`](../tests/test_f05_waypoints.py). [Implementation PR #11](https://github.com/nestrada88/gpx-processing-pipeline/pull/11) was merged.

The input is an F01 `GPXDocument`, and F02 `validate_spatial(document).valid` is required. All annotations live in returned frozen dataclasses: GPX coordinates, waypoint ordering and source XML fields are not rewritten. The module is offline-first; reverse geocoding is optional and provided by the caller. It does not configure Garmin navigation or alert behavior.

## Public API

```python
enrich_waypoints(
    document: GPXDocument,
    *,
    categories: Mapping[int, str] | None = None,
    checkpoints: Mapping[int, int] | None = None,
    proximity_threshold_m: float = 100.0,
    reverse_geocoder: Callable[[float, float], str | None] | None = None,
) -> WaypointCatalog
```

These identifiers are exported by `gpx_pipeline` and `gpx_pipeline.waypoints`: `WaypointError`, `WaypointFinding`, `WaypointCatalogEntry`, `WaypointCatalog`, and `enrich_waypoints`.

### Result contracts

- `WaypointCatalog(entries: tuple[WaypointCatalogEntry, ...], findings: tuple[WaypointFinding, ...])` contains catalog entries in original top-level GPX waypoint order and nonfatal diagnostic findings.
- `WaypointCatalogEntry` fields:
  - `index: int`: zero-based standalone `<wpt>` position.
  - `latitude: float`, `longitude: float`: original WGS 84 geographic coordinates in decimal degrees.
  - `name: str | None`, `description: str | None`, `symbol: str | None`, `recorded_type: str | None`: original GPX `name`, `desc`, `sym`, and `type` child text, respectively. No value is inferred if its source is absent.
  - `category: str`: explicitly supplied user category or `"unclassified"`.
  - `checkpoint_order: int | None`: explicit, positive, unique user-defined order, otherwise `None`.
  - `nearest_vertex_m: float | None`: minimum F02 WGS 84 geodesic distance in meters from this waypoint to any recorded track or route **vertex**, or `None` if no such vertices exist.
  - `near_route: bool | None`: `nearest_vertex_m <= proximity_threshold_m` when vertices exist; `None` when no vertices exist.
  - `place_label: str | None`: optional reverse-geocoder result, otherwise `None`.
  - `provenance: tuple[str, ...]`: origin tags for the waypoint and added annotations.
- `WaypointFinding(code: str, waypoint: int)` uses zero-based waypoint index. Unlike F04, this finding type has no severity field.

A GPX document with no standalone waypoints produces an empty catalog. Track points (`<trkpt>`) and route points (`<rtept>`) contribute proximity targets only, not waypoint catalog entries. No duplicate suppression or automatic reordering occurs.

## Configuration and fail-closed validation

| Input | Implemented validation |
| --- | --- |
| `proximity_threshold_m` | Must be finite and nonnegative; zero is permitted. Invalid values raise `ValueError`. |
| `categories` | Keys must reference existing zero-based waypoint indices. Values must be nonempty strings after `strip()` testing. Invalid keys/values raise `WaypointError`. The original string is retained as entered rather than stripped or normalized. |
| `checkpoints` | Keys must reference existing waypoint indices; values must be actual Python `int` (not `bool`), strictly positive, and unique. Nonconsecutive ordering is permitted. Invalid keys/values raise `WaypointError`. |
| `reverse_geocoder` | Must be `None` or callable; otherwise `TypeError`. A callback receives `(latitude, longitude)` and may return `str` or `None`. |
| `document` | F02 spatial validation must pass or `WaypointError("F02 spatial validation failed")` is raised. |

The mapping arguments are copied before processing; there is no built-in taxonomy or hazard classifier. Providing `"hazard"` is a caller assertion, **not an independently established safety condition**. An empty-string geocoder result is accepted as a string and can produce `external:geocoder` provenance; it should not be interpreted as a meaningful verified location.

## Nearest-vertex proximity: exact meaning and limitations

The implementation gathers recorded vertices from all GPX track segments followed by all GPX routes; it does not join segments into new edges. For waypoint `w` and the finite set of recorded vertices `V`, it computes:

```text
nearest_vertex_m(w) = min(geodesic_distance_m(w, v) for v in V)
near_route(w)       = nearest_vertex_m(w) <= proximity_threshold_m
```

Geodesic distances use F02 `geodesic_distance_m` with coordinate order `(latitude, longitude)`. The threshold is expressed in meters; it defaults to **100.0 m** and the comparison is inclusive.

This is **point-to-vertex** distance, not point-to-polyline/segment projection, cross-track distance, along-trail distance, network accessibility or a hazard proximity assessment. For sparse or heavily simplified GPX geometry, an observation could lie near a line connecting two recorded points and nonetheless be classified far from every vertex. Source geometry takes precedence over implied paths. No DEM information, terrain obstruction, river crossing, or navigability is considered.

When `V` is empty, `nearest_vertex_m=None`, `near_route=None`, and `NO_ROUTE_VERTICES` is recorded **for each waypoint**. Unknown proximity is never converted to `False`.

The direct implementation scans every waypoint against every collected vertex; it does not use a spatial index. Its work therefore scales approximately with the product of waypoint and vertex counts and can be costly for large inputs.

## Optional reverse geocoding and failure isolation

If a caller passes `reverse_geocoder`, F05 calls it once for each waypoint in waypoint order with its latitude and longitude. A returned `str` is copied into `place_label`; `None` leaves the label absent. A non-string, non-`None` return, or any exception raised by the callback, is caught and recorded as `GEOCODING_FAILED` for that waypoint, leaving `place_label=None` while retaining its original GPX content.

F05 has **no built-in network client, geocoding service, cache, language selection or external data verification**. Callback latency, privacy, licensing, rate limiting and reproducibility depend on the caller-supplied provider. Fixed source coordinates and deterministic callback behavior yield repeatable catalog results; a changing external geocoder may not.

## Provenance tags and diagnostics

Each entry starts with `"gpx:waypoint"`. Further tags are appended in the following implementation order, when applicable:

| Tag | Condition and meaning |
| --- | --- |
| `gpx:waypoint` | Entry came from an original GPX standalone waypoint. |
| `user:classification` | Waypoint index appears in the explicit `categories` mapping. |
| `user:checkpoint_order` | Waypoint index appears in `checkpoints`. |
| `derived:wgs84_nearest_vertex` | At least one track or route vertex exists, so a geodesic vertex distance was derived. |
| `external:geocoder` | Optional callback returned a non-`None` string. |

These tags distinguish source and annotation origins; they are not cryptographic provenance, provider attribution, accuracy certifications or an audit log.

| Finding code | Trigger | Result |
| --- | --- | --- |
| `NO_ROUTE_VERTICES` | No track/route vertices available | `nearest_vertex_m=None`, `near_route=None`; original waypoint retained. |
| `GEOCODING_FAILED` | Callback raises or returns a value other than `str` or `None` | `place_label=None`; original waypoint retained. |

Invalid configuration or invalid upstream spatial data raises an exception, rather than returning a `WaypointFinding`. The implementation does not produce inferred-danger or unknown-category findings. `WaypointCatalog` has no `valid` or `complete` property.

## Reproducible usage

The following example is self-contained and requires no online service:

```python
from gpx_pipeline import enrich_waypoints, parse_gpx, serialize_gpx

source = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1"
     version="1.1" creator="f05-example">
  <wpt lat="12" lon="-86">
    <name>Start</name><desc>Recorded observation</desc><sym>Flag</sym>
  </wpt>
  <trk><trkseg>
    <trkpt lat="12" lon="-86"/>
    <trkpt lat="12.01" lon="-86"/>
  </trkseg></trk>
</gpx>"""

document = parse_gpx(source, strict=False)
before = serialize_gpx(document)
catalog = enrich_waypoints(
    document,
    categories={0: "checkpoint"},
    checkpoints={0: 1},
    proximity_threshold_m=50.0,
    reverse_geocoder=lambda lat, lon: "Local reference",
)

entry = catalog.entries[0]
assert entry.index == 0
assert entry.name == "Start"
assert entry.category == "checkpoint"
assert entry.checkpoint_order == 1
assert entry.nearest_vertex_m == 0.0
assert entry.near_route is True
assert entry.place_label == "Local reference"
assert serialize_gpx(document) == before
print(entry, catalog.findings)
```

Here the waypoint coincides with a recorded track vertex. `strict=False` controls F01 parsing mode, while F05 still requires F02 spatial validation. The geocoder is an illustrative local callback, not a real place lookup.

## Verification evidence and unimplemented capabilities

The committed [F05 tests](../tests/test_f05_waypoints.py) exercise source metadata and original GPX serialization preservation, explicit classifications/checkpoints, vertex-nearness and distance threshold, missing route geometry, geocoder failure isolation, invalid configuration and F02 spatial rejection, and repeatability of unclassified outputs. The tests are present in source; their existence and PR merge status do **not** establish a new successful test execution. To verify in a configured checkout, run `python -m pytest -q` and examine the CI results.

Not implemented in this module: automatic hazard verification, continuous-polyline nearest projection, path accessibility, DEM-derived waypoint characteristics, reverse-geocoding provider setup, geographic place-label quality checks, waypoint deduplication, Garmin alert configuration or device alert guarantees. Downstream F06 analytical processing and F07 export must not interpret vertex-nearness as surveyed trail proximity or imply alert capabilities from catalog labels.

## Related files

- [F01 interoperability documentation](domains/F01-gpx-interoperability.md)
- [F02 spatial integrity documentation](F02-SPATIAL-INTEGRITY.md)
- [F05 implementation](../src/gpx_pipeline/waypoints.py)
- [F05 tests](../tests/test_f05_waypoints.py)
- [F05 implementation PR #11](https://github.com/nestrada88/gpx-processing-pipeline/pull/11)

This is a documentation-only artifact; it does not introduce runtime, test, package, or CLI changes.
