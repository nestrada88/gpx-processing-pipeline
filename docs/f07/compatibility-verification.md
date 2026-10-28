# F07-B — Garmin Export Compatibility Verification

[← F07 overview](../F07-GARMIN-NAVIGATION-EXPORT.md)

## Purpose and interface

The offline verifier independently checks a generated `NavigationExportResult` against its original GPX source, local schema evidence and the **selected transfer workflow**. It does not upload to Garmin Connect/Explore or test a physical navigator.

Implementation: [`src/gpx_pipeline/garmin_compatibility.py`](../../src/gpx_pipeline/garmin_compatibility.py); tests: [`tests/test_f07_garmin_compatibility.py`](../../tests/test_f07_garmin_compatibility.py); [PR #19](https://github.com/nestrada88/gpx-processing-pipeline/pull/19).

```python
verify_garmin_export(
    source: GPXDocument,
    exported: NavigationExportResult,
    *,
    options: GarminCompatibilityOptions = GarminCompatibilityOptions(),
    schemas: GarminSchemaRegistry | None = None,
) -> GarminCompatibilityResult

garmin_verification_json(result: GarminCompatibilityResult) -> bytes
```

`GarminCompatibilityOptions(workflow="explore-web-tracks", require_xsd=True)` accepts only `"explore-web-tracks"`, `"explore-web-routes"`, and `"connect-course"`; `require_xsd` must be `bool`. Invalid values raise `ValueError`.

`GarminSchemaRegistry(gpx11_xsd: Path | None=None, extensions: dict[str,Path] | None=None)` supplies local GPX/extension schema paths and can create the F01 registry through `as_registry()`. No schema is fetched remotely.

## Result structures and status semantics

- `GarminVerificationFinding(code, severity, explanation)` has `severity` in `"error"`, `"unverified"`, `"info"`.
- `GeometryVerificationResult(exact_coordinate_and_segment_match, exact_waypoint_xml_match, source_geometry_sha256, exported_geometry_sha256, checkpoint_map_preserved)` records independent audit flags.
- `TransferCompatibilityResult(workflow, track_points_limit, route_points_limit, waypoint_import_limit, within_known_limits)` distinguishes an applicable workflow's known constraints from unknown values (`None`).
- `GarminCompatibilityResult` includes `schema_version`, `device_id`, `software_status`, `physical_device_verified`, source/export SHA-256 values, `schema_validated`, optional geometry audit, transfer findings and all diagnostic records.
- `garmin_verification_json` serializes deterministic finite-only UTF-8 JSON with sorted keys, compact separators and trailing newline.

Software status:
- `incompatible` whenever any finding has severity `error`.
- Otherwise `unverified` when any finding has severity `unverified`.
- Otherwise `validated` when there are no error/unverified findings.

**Critical boundary:** `validated` means the performed *software* checks produced no blocking or unverified findings; it never proves Garmin import or physical navigation. This implementation always returns `physical_device_verified=False`.

## Integrity verification

The verifier recomputes SHA-256 from `source.xml` and `exported.gpx` and compares them with export result metadata. It reparses exported XML, checks version/creator, compares source/export ordered track/route coordinate-string and segment structure, and checks canonicalized waypoint XML for changes in names and other waypoint content. It also validates the checkpoint manifest's positive unique orders, valid original waypoint indexes and sorted order.

A geometry fingerprint mismatch, source/export hash mismatch, changed waypoint XML, invalid checkpoint manifest or malformed export creates an explicit error finding. Input-dependent problems are usually reported through `findings` and `software_status`, not silently repaired. The verification geometry checks do not measure post-import Garmin course behavior.

## Workflow-specific transfer constraints

| Workflow | Target profile | Track/route points per imported line | Waypoints per website import |
| --- | --- | --- | --- |
| `explore-web-tracks` | `etrex-se` | 10,000 | 500 |
| `explore-web-routes` | `etrex-se` | 200 | 500 |
| `connect-course` | `instinct-2x-tactical` | Unknown | Unknown |

Limits for Explore are explicitly modeled as **Explore website import-mode** ceilings. The selected line limit applies to GPX tracks and routes, counting track points across the track's segments. More points than the limit generates `EXPLORE_LINE_LIMIT_EXCEEDED` (`error`), and more than 500 waypoints generates `EXPLORE_WAYPOINT_IMPORT_LIMIT_EXCEEDED` (`error`). Multi-segment track conversion in `explore-web-routes` generates `SEGMENT_TO_ROUTE_CONVERSION_UNVERIFIED` (`unverified`).

Connect produces `CONNECT_POINT_LIMIT_UNVERIFIED` (`unverified`), with no invented numeric ceiling. Device/workflow mismatch produces `PROFILE_WORKFLOW_MISMATCH` (`error`). These workflow ceilings are not the same as the separate exporter profile's eTrex 1,000-waypoint device field.

## Schema behavior: fail closed when required

The default `require_xsd=True` means a missing local authoritative GPX 1.1 XSD yields `GPX_XSD_UNAVAILABLE` (`unverified`) **and** `REQUIRED_XSD_NOT_VALIDATED` (`error`), making software status `incompatible`. With `require_xsd=False`, the missing XSD still leaves status `unverified` unless another error is present.

With supplied `GarminSchemaRegistry`, the verifier invokes strict F01 parsing and locally registered extension schemas. It reports `GPX_XSD_INVALID` for validation failures. Any non-GPX namespace without a locally registered extension schema generates `EXTENSION_SCHEMA_UNAVAILABLE` (`error`) regardless of GPX lax extension allowances. **A synthetic XSD used by a test proves only that validation wiring works, not compliance with the authoritative GPX 1.1 standard.** The exporter itself currently rejects populated extension elements.

Examples of error findings include `SOURCE_HASH_MISMATCH`, `EXPORT_HASH_MISMATCH`, `GPX_HEADER_INVALID`, `NAVIGATION_GEOMETRY_OR_WAYPOINT_CHANGED`, `CHECKPOINT_MAP_INVALID`, `GEOMETRY_AUDIT_MISMATCH`, `EXPORT_XML_INVALID` and `PROFILE_WORKFLOW_MISMATCH`. Report all findings rather than inferring device success from a single status.

## Executable usage fragment

This example intentionally disables mandatory XSD for a limited **offline software assessment**; it does **not** claim strict schema or Garmin device verification.

```python
from pathlib import Path
from gpx_pipeline import (
    GarminCompatibilityOptions, NavigationExportOptions,
    export_garmin_navigation, garmin_verification_json,
    parse_gpx, verify_garmin_export,
)

source = parse_gpx(Path("route.gpx").read_bytes(), strict=False)
exported = export_garmin_navigation(
    source, options=NavigationExportOptions(device_id="etrex-se")
)
result = verify_garmin_export(
    source, exported,
    options=GarminCompatibilityOptions(
        workflow="explore-web-tracks", require_xsd=False
    ),
)
print(result.software_status, result.physical_device_verified)
print([f.code for f in result.findings])
Path("etrex-compatibility.json").write_bytes(garmin_verification_json(result))
```

For strict validation, supply a correctly configured local GPX 1.1 XSD with `GarminSchemaRegistry(gpx11_xsd=Path("GPX1.1.xsd"))` and use the default `require_xsd=True`. Obtain and verify authoritative schema inputs independently; no bundled file is assumed in this example.

## Verification scope and limitations

The [compatibility tests](../../tests/test_f07_garmin_compatibility.py) cover geometry/hash/manifest checks, missing and invalid schema behavior, synthetic local XSD wiring, Explore point/waypoint limits, multi-segment conversion uncertainty, unknown Connect limits, profile-workflow mismatches, corrupted XML, tampering and unknown extension schemas. These are offline regression tests, not physical-device measurements.

External Garmin import transforms, Garmin Explore mobile-app limitations, actual course-point truncation, navigation alerts, off-course notifications, device transfer success and offline field performance are not verified. The downstream F08 production schema domain and F10 field-evidence domain own those distinct responsibilities.
