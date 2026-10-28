# F10 — Field Evidence Contract

[← F10 overview](../F10-OPERATIONAL-RELIABILITY.md) · [Manual field procedure](../f10-field-validation.md)

Implementation: [`src/gpx_pipeline/field_evidence.py`](../../src/gpx_pipeline/field_evidence.py). Tests: [`tests/test_f10_reliability.py`](../../tests/test_f10_reliability.py).

## Scope

This module models **human-supplied** observations from real Garmin field testing. It does not connect to a device, load Garmin telemetry, execute an import, attest that an observation was genuinely performed, or automatically mark F09 software readiness as hardware-tested.

F10 interfaces are imported directly from `gpx_pipeline.field_evidence`, not from the package root in the inspected implementation.

## Immutable Python contracts

```python
@dataclass(frozen=True, slots=True)
class FieldObservation:
    check: str
    outcome: str
    evidence_reference: str | None
    notes: str = ""

@dataclass(frozen=True, slots=True)
class FieldEvidenceRecord:
    device_id: str
    firmware: str
    transfer_workflow: str
    source_sha256: str
    export_sha256: str
    observations: tuple[FieldObservation, ...]

    def matches(self, source: bytes, exported: bytes) -> bool: ...

def field_evidence_json(record: FieldEvidenceRecord) -> bytes: ...
```

### Permitted observation types

| `check` | Intended physical observation |
| --- | --- |
| `explore_connect_import` | Outcome of Garmin Explore/Connect GPX import |
| `device_course_present` | Whether imported course appears on actual device |
| `course_geometry` | Observed course geometry after conversion |
| `mandatory_checkpoints` | Presence/order of mandatory checkpoint behavior |
| `offline_navigation` | Navigation without network/mobile assistance |
| `off_course_alert` | Safe controlled off-course detection/feedback |
| `independent_backup` | Secondary device navigates independently |

Only `"passed"`, `"failed"`, or `"unverified"` are permitted values of `outcome`. For `passed` or `failed`, a nonempty `evidence_reference` is mandatory. For `unverified`, `evidence_reference=None` is accepted. References consisting only of whitespace are rejected, including when an observation is unverified. Notes have a maximum length of 2,048 characters and evidence references a maximum length of 1,024 characters.

### Record constraints

- `device_id` must be `"etrex-se"` or `"instinct-2x-tactical"`.
- `firmware` must be nonblank (after stripping) and at most 128 characters.
- `transfer_workflow` must be `"explore-web-tracks"`, `"explore-web-routes"` or `"connect-course"`.
- An eTrex record requires an Explore workflow; an Instinct 2X Tactical record requires Connect course workflow.
- Both digest strings must be lowercase hexadecimal SHA-256 with exactly 64 characters.
- A record cannot contain duplicate `check` entries. Missing observations are **not automatically synthesized**; an empty tuple is structurally permitted.
- `matches(source, exported)` recomputes both hashes from provided bytes and checks for equality with the recorded digests. It does not authenticate a device, firmware claim, evidence file, timestamp or human observation.
- `field_evidence_json` creates deterministic UTF-8 JSON with sorted keys, compact separators and trailing newline; it uses no wall-clock timestamp by default.

## Reproducible example without fabricated physical outcomes

```python
from pathlib import Path
from hashlib import sha256
from gpx_pipeline.field_evidence import (
    FieldObservation, FieldEvidenceRecord, field_evidence_json,
)

source = Path("route.gpx").read_bytes()
exported = Path("etrex-se.gpx").read_bytes()

record = FieldEvidenceRecord(
    device_id="etrex-se",
    firmware="REPLACE_WITH_DEVICE_FIRMWARE",
    transfer_workflow="explore-web-tracks",
    source_sha256=sha256(source).hexdigest(),
    export_sha256=sha256(exported).hexdigest(),
    observations=(
        FieldObservation(
            check="explore_connect_import",
            outcome="unverified",
            evidence_reference=None,
        ),
        FieldObservation(
            check="offline_navigation",
            outcome="unverified",
            evidence_reference=None,
        ),
    ),
)
assert record.matches(source, exported)
Path("etrex-field-evidence.json").write_bytes(field_evidence_json(record))
```

Both GPX paths are illustrative and must refer to actual source/export file bytes. Replace firmware placeholder with the exact measured device firmware **before representing the record as genuine device evidence**. Until an observation is physically executed, leave its outcome `unverified`. To record a true `passed` or `failed` result, cite a stable local evidence reference identifying actual observations (e.g., a file record, log or measured artifact) and keep the evidence itself separately.

## Interpretation and integration

`FieldEvidenceRecord` is an evidence **data model**, not an automatic verified status. It can faithfully store an incorrect statement if the supplied notes/reference are misleading. It does not modify `OperationalReadiness.physical_transfer_verified` or `physical_navigation_verified`; the software verifier always reports those as false.

F09 currently emits software readiness reports via `verification/<device>-operational.json`; it does not generate field-evidence JSON without explicit human input or import evidence into the pipeline. For practical device observations, use the existing [manual field-validation procedure](../f10-field-validation.md). A screenshot may help document display appearance, but it should not be misrepresented as a byte-exact post-Garmin course geometry comparison when export is unavailable.

## Validation and regression evidence

`tests/test_f10_reliability.py` verifies digest matching and mismatch detection, the mandatory evidence reference for passed/failed outcomes, invalid firmware or digest rejection, duplicate-check rejection, and the serialized representation of an unverified observation.

These tests validate model behavior with synthetic bytes; they do **not** exercise real Garmin devices or establish that a supplied evidence reference exists. No test execution or physical observation is claimed by this documentation.
