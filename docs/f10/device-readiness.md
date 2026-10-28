# F10 — Operational Device Readiness

[← F10 overview](../F10-OPERATIONAL-RELIABILITY.md) · [Manual field procedure](../f10-field-validation.md)

Implementation: [`src/gpx_pipeline/operational_verification.py`](../../src/gpx_pipeline/operational_verification.py). Tests: [`tests/test_f10_reliability.py`](../../tests/test_f10_reliability.py).

## Public API and result

```python
from gpx_pipeline.operational_verification import (
    ETREX_SE_COURSE_POINT_LIMIT,
    ETREX_SE_STORED_COURSE_LIMIT,
    OperationalFinding,
    OperationalReadiness,
    verify_device_readiness,
)

verify_device_readiness(
    source: GPXDocument,
    exported: NavigationExportResult,
) -> OperationalReadiness
```

The immutable `OperationalFinding` contains `code: str`, `severity: str`, and `detail: str`. `OperationalReadiness` carries `device_id: str`, `software_compatible: bool`, `physical_transfer_verified: bool`, `physical_navigation_verified: bool`, and `findings: tuple[OperationalFinding, ...]`.

The implementation always sets both physical flags `False`. `software_compatible` is `not any(f.severity == "error" for f in findings)`; the presence of `unverified` findings does **not** by itself make `software_compatible=False`. This status is a limited software gate, not a physical test certificate.

## eTrex SE conservative device constraints

- `ETREX_SE_COURSE_POINT_LIMIT = 200`.
- `ETREX_SE_STORED_COURSE_LIMIT = 50`.
- Every source GPX `trk` is one candidate course line, with points **summed across its `trkseg` elements**. Every `rte` is one additional candidate course line.
- More than 50 source lines yields `ETREX_COURSE_COUNT_EXCEEDED` (`error`).
- More than 200 points for any one candidate line yields `ETREX_COURSE_POINT_LIMIT_EXCEEDED` (`error`).
- A track containing more than one source segment yields `ETREX_SEGMENT_CONVERSION_UNVERIFIED` (`unverified`), since Garmin Explore conversion may alter source topology.

These are conservative pre-transfer limits. Garmin's source website import limits and its actual post-import course representation are distinct. Reference for published eTrex course constraints: https://support.garmin.com/da-DK/?faq=Hg2pM7ov4oAql6IzzaB398 . Two independent 150-point tracks count as two within-limit candidates; a single 201-point track fails. Neither passing case proves Explore conversion fidelity.

## Instinct 2X Tactical and unknown targets

For `instinct-2x-tactical`, no numerical eTrex limit is borrowed. The function reports `INSTINCT_COURSE_LIMIT_UNVERIFIED` (`unverified`) because a reliable fixed course-point ceiling was not encoded.

An unrecognized device profile produces `UNKNOWN_DEVICE` (`error`); ordinary F07 target selection already rejects unknown profile IDs.

Every return adds `FIELD_DEVICE_TEST_UNVERIFIED` (`unverified`) regardless of model. No populated field record changes this method's computed flags: it does not accept or evaluate `FieldEvidenceRecord`.

## Diagnostic map

| Code | Severity | Meaning |
| --- | --- | --- |
| `ETREX_COURSE_COUNT_EXCEEDED` | `error` | More than 50 source track/route candidate courses |
| `ETREX_COURSE_POINT_LIMIT_EXCEEDED` | `error` | More than 200 points in an eTrex candidate course |
| `ETREX_SEGMENT_CONVERSION_UNVERIFIED` | `unverified` | Multiple source segments may be transformed by conversion |
| `INSTINCT_COURSE_LIMIT_UNVERIFIED` | `unverified` | No verified numerical Instinct course capacity encoded |
| `UNKNOWN_DEVICE` | `error` | Export profile is unsupported |
| `FIELD_DEVICE_TEST_UNVERIFIED` | `unverified` | Device import, offline navigation and alerts lack measured evidence |

## Direct Python usage

```python
from pathlib import Path
from gpx_pipeline import parse_gpx
from gpx_pipeline.garmin_export import (
    NavigationExportOptions, export_garmin_navigation,
)
from gpx_pipeline.operational_verification import verify_device_readiness

source = parse_gpx(Path("route.gpx").read_bytes(), strict=False)
exported = export_garmin_navigation(
    source, options=NavigationExportOptions(device_id="etrex-se")
)
readiness = verify_device_readiness(source, exported)
print(readiness.software_compatible)
print([finding.code for finding in readiness.findings])
assert not readiness.physical_navigation_verified
```

The supplied route file must be real, spatially valid and navigable; the example is a method demonstration, not a physical-device test. `parse_gpx(strict=False)` alone does not mean F08 production XSD validation was executed; for fully orchestrated validation/export use F09 `gpx-pipeline export`.

## F09 interaction and failure boundary

F09 calls `verify_device_readiness(document, export)` for each selected target after F07 export and F08-backed verification. On `software_compatible=False`, F09 raises `PipelineError("GARMIN_INCOMPATIBLE", ...)`; the CLI returns exit code **5** and does not publish the destination. On success it serializes the dataclass as deterministic compact sorted-key JSON (ending newline) into `verification/<device>-operational.json` and publishes alongside the GPX, its export manifest and separate F07 compatibility report. `analyze` remains an independent command even if the same source cannot be exported to eTrex.

F10 does not change source GPX coordinates, simplify over-limit courses, produce FIT, synchronize devices, infer Garmin alerts or certify physical course transfer. Device compatibility remains subject to real Garmin import and offline testing; follow the [manual procedure](../f10-field-validation.md).
