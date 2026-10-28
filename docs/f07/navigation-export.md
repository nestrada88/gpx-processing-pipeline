# F07-A — Garmin Navigation Export

[← F07 overview](../F07-GARMIN-NAVIGATION-EXPORT.md)

## Implementation and public API

Implementation: [`src/gpx_pipeline/garmin_export.py`](../../src/gpx_pipeline/garmin_export.py); regression tests: [`tests/test_f07_garmin_export.py`](../../tests/test_f07_garmin_export.py); [PR #18](https://github.com/nestrada88/gpx-processing-pipeline/pull/18).

```python
export_garmin_navigation(
    source: GPXDocument,
    *,
    options: NavigationExportOptions = NavigationExportOptions(),
    waypoints: WaypointCatalog | None = None,
    registry: SchemaRegistry | None = None,
) -> NavigationExportResult

export_garmin_pair(
    source: GPXDocument,
    *,
    waypoints: WaypointCatalog | None = None,
    registry: SchemaRegistry | None = None,
    require_strict_xsd: bool = False,
) -> tuple[NavigationExportResult, NavigationExportResult]
```

The exported types are `GarminExportError`, `GarminDeviceProfile`, `NavigationExportOptions`, `GarminCompatibilityFinding`, `NavigationGeometryAudit`, `NavigationExportResult`, `ETREX_SE`, `INSTINCT_2X_TACTICAL` and the two functions above.

### Device profiles and options

`NavigationExportOptions(device_id="etrex-se", require_strict_xsd=False)` defaults to eTrex SE without requested strict XSD. Only `"etrex-se"` and `"instinct-2x-tactical"` are accepted; unknown profiles raise `ValueError`.

`GarminDeviceProfile(device_id, product_name, transfer_path, waypoint_limit)` distinguishes known and unknown **device-profile** waypoint limits. Current profiles: `ETREX_SE.waypoint_limit=1000`, `INSTINCT_2X_TACTICAL.waypoint_limit=None`. Unknown is not unlimited. These device-profile values do not replace Garmin Explore website import-mode checks performed by the separate verifier.

### Result contracts

- `NavigationExportResult.gpx: bytes`: exported GPX 1.1 XML.
- `profile: GarminDeviceProfile`: selected target profile.
- `source_sha256: str`, `export_sha256: str`: SHA-256 of `source.xml` and exported bytes.
- `audit: NavigationGeometryAudit`: track count, track-segment count, trackpoint count, route/routepoint count, waypoint count, geometry fingerprint and `exact_geometry_match`.
- `checkpoints: tuple[tuple[int,int], ...]`: ordered `(checkpoint_order, original_waypoint_index)` pairs, **not** inserted into GPX.
- `findings: tuple[GarminCompatibilityFinding, ...]`: `code`, `severity` and `explanation`.
- `manifest() -> bytes`: deterministic UTF-8 JSON of the result metadata **without** embedded `gpx`; sorted keys, compact separators and a final newline.

The geometry fingerprint is SHA-256 over canonical JSON of original track/route coordinate strings and segment boundaries plus waypoint coordinate strings and names. It is not a fingerprint of all source XML or a proof of Garmin import fidelity.

## Processing and invariants

1. Apply F02 `validate_spatial(source)`; invalid geometry raises `GarminExportError`.
2. Validate a conservative subset of GPX 1.1 child elements and required ordering at top level, track, route, segment and point levels. Unsupported/unknown extension namespaces and populated `<extensions>` are rejected. Metadata/link internal structures are not fully assured by this subset and need strict XSD evidence.
3. If `require_strict_xsd=True`, require a supplied `SchemaRegistry` with a local GPX 1.1 XSD. When a registry includes that XSD, source GPX is also parsed strictly. No schema is downloaded.
4. Require at least one track segment with at least two track points or a route with at least two route points. Standalone waypoints or singleton geometry do not qualify.
5. Enforce any **known device-profile** waypoint limit. Validate optional F05 catalog against original waypoint count, index, latitude, longitude and name, then reject invalid or duplicate checkpoint orders.
6. Preserve the source GPX tree and set only the root `creator` to `gpx-processing-pipeline/<device-id>`. Serialize GPX XML as UTF-8.
7. Reparse the export (strictly only if requested), re-run F02 spatial validation, and compare coordinate **strings**, tracks, routes, segments and waypoint geometry/topology. Reject any geometry mismatch.
8. Return bytes, manifest metadata and explicit verification findings. `export_garmin_pair` repeats this per target, ordered eTrex SE then Instinct 2X Tactical.

The exporter does **not** translate a source track to a route or a route to a track; it does not synthesize course turns, timestamps, speed data, Garmin XML extensions, FIT courses, or physical device settings. Recorded waypoint XML and geometry are preserved as source, but complete byte-for-byte equality of all GPX XML is not claimed because root creator and serialization may change.

## Findings and schema caveats

Successful export always reports:
- `DEVICE_TRANSFER_UNVERIFIED` (`verification_required`): actual Garmin application/device transfer is not tested.
- `COURSE_CONVERSION_UNVERIFIED` (`verification_required`): Garmin conversion could alter topology.
- `NAVIGATION_ALERTS_UNVERIFIED` (`verification_required`): file generation does not guarantee alerts.

It additionally reports `XSD_NOT_VERIFIED` when `require_strict_xsd=False`, and `WAYPOINT_LIMIT_UNKNOWN` (`informational`) for device profiles without an encoded waypoint limit. These are export **findings**, not the separate compatibility verifier's `software_status`.

Strict XSD requires a valid caller-supplied local schema; a successful non-strict export is **not proof of GPX 1.1 XSD conformance**. The exporter and offline verifier use separate XSD options: see [compatibility verification](compatibility-verification.md).

## Executable usage fragment

Given an existing valid GPX file, and without relying on an online Garmin service:

```python
from pathlib import Path
from gpx_pipeline import (
    NavigationExportOptions, export_garmin_navigation,
    export_garmin_pair, parse_gpx,
)

source = parse_gpx(Path("route.gpx").read_bytes(), strict=False)
etrex = export_garmin_navigation(
    source,
    options=NavigationExportOptions(
        device_id="etrex-se", require_strict_xsd=False
    ),
)
Path("etrex-se.gpx").write_bytes(etrex.gpx)
Path("etrex-se-manifest.json").write_bytes(etrex.manifest())
print(etrex.audit.exact_geometry_match, [f.code for f in etrex.findings])

both = export_garmin_pair(source)
assert len(both) == 2
```

`route.gpx` must contain navigable valid track/route geometry; it is not supplied by the repository. The example makes no XSD, transfer or hardware-validation claim.

## Verification and limits

The [export tests](../../tests/test_f07_garmin_export.py) cover independent target outputs, exact source/export geometry and stable bytes, checkpoint preservation, device waypoint-limit distinction, route support, malformed/non-navigable source rejection, invalid coordinate and extension rejection, malformed ordering, strict-XSD configuration and unverified behaviors.

There is no automatic rerouting, course simplification, proximity-alert setup, GPX extension synthesis, Garmin Connect import, Garmin Explore import, device transfer, recorded-on-device fidelity check or physical navigation validation. Import-mode ceilings are validated separately by `verify_garmin_export`. Regression test presence and PR merge are not fresh test-execution evidence.
