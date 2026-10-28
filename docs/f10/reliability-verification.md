# F10 — Reliability Verification and Regression Evidence

[← F10 overview](../F10-OPERATIONAL-RELIABILITY.md) · [Field procedure](../f10-field-validation.md)

Implementation and tests: [`tests/test_f10_reliability.py`](../../tests/test_f10_reliability.py), [`operational_verification.py`](../../src/gpx_pipeline/operational_verification.py), [`field_evidence.py`](../../src/gpx_pipeline/field_evidence.py), [`output.py`](../../src/gpx_pipeline/output.py), and [`pipeline.py`](../../src/gpx_pipeline/pipeline.py).

## Evidence classification

| Evidence level | What is checked | What it cannot establish |
| --- | --- | --- |
| Unit/regression tests | Deterministic predicates and known edge conditions | Actual Garmin firmware/import behavior |
| CLI integration | Input rejection, error code and generated report | On-device course fidelity or alert settings |
| Output fault injection | Controlled staged-file interruption cleanup | Recovery from all power-loss/storage failures |
| Numerical reference | One WGS84 benchmark | Comprehensive geodesic/DEM correctness |
| Manual field record | User-reported physical observations tied to source/export hashes | Independent authenticity beyond supplied evidence |

The tests and merged [implementation PR #22](https://github.com/nestrada88/gpx-processing-pipeline/pull/22) exist. Test code inspection alone is not a claim that the present checkout or CI was rerun successfully.

## Known device-capacity boundary tests

The parametrized eTrex test uses 2, 199, 200, 201 and 10,000 track points. Its expected software readiness is True through 200 and False above 200; in rejected cases `ETREX_COURSE_POINT_LIMIT_EXCEEDED` must appear.

Separate tests verify:
- Two independent 150-point tracks remain individually under the per-course limit.
- Exactly 50 candidate courses pass the stored-course count, while 51 fail with `ETREX_COURSE_COUNT_EXCEEDED`.
- A 201-point Instinct 2X Tactical source is not incorrectly rejected using eTrex's 200-point limit; `INSTINCT_COURSE_LIMIT_UNVERIFIED` remains visible.
- A 201-point eTrex CLI export returns exit code **5**, includes the relevant diagnostic on stderr, and creates no destination directory.
- An `analyze` run for the same dense source still succeeds and retains 201 recorded track points in the canonical analytical dataset. F06 analysis has precedence over Garmin navigation capacity restrictions.
- A valid eTrex export publishes `verification/etrex-se-operational.json` with `software_compatible=True` but physical transfer/navigation flags set to False.
- A multi-segment track produces `ETREX_SEGMENT_CONVERSION_UNVERIFIED` without falsely claiming that Explore preserves or changes its geometry.

These tests check modeled source-line limits, not a complete simulation of Garmin application course conversion.

## Publication fault injection

F10 monkeypatches `gpx_pipeline.output.os.fsync` to raise `OSError("simulated write interruption")` inside `publish_outputs`. The test expects an `OutputError`, no published destination, and no remaining `.gpx-stage-*` temporary directory in the output parent. It also compares manifests across separate directories for identical artifact bytes, command and input hashes.

Actual F09 publication stages files beside the final directory, flushes and fsyncs files, checks SHA-256 after writing, then renames the staging directory on the same filesystem where supported. This provides bounded integrity and cleanup guarantees for the tested failure path; it does not guarantee directory fsync, universally atomic behavior across all filesystems, full crash durability, absence of external races or protection against malicious filesystem interference.

See [F09 output publication](../f09/output-publication.md).

## WGS84 numerical sanity reference

A regression test uses `geodesic_distance_m(0, 0, 0, 1)` with WGS84 equatorial distance reference **111,319.49079327357 metres**, checking absolute tolerance of **0.002 metres** and zero relative tolerance. This is one fixed numerical sanity reference for F02 geodesics, not a proof of accuracy for every coordinate, edge, longitude wrapping or DEM uncertainty scenario.

## Evidence model regression checks

F10 regression tests assert:
- `FieldEvidenceRecord.matches` succeeds for original/exported bytes and fails when exported bytes are altered.
- `FieldObservation(outcome="passed")` without evidence reference is rejected.
- Missing firmware or malformed digest is rejected.
- Duplicate observation check names in one record are rejected.
- `unverified` observations can be serialized without inventing a physical result.

The evidence model checks formatting and declared file identity, not actual validity of external proof. See [field evidence contract](field-evidence-contract.md).

## Reproducing the software tests

In a configured Python >=3.11 checkout with dependencies:

```bash
python -m pip install -e '.[test]'
python -m pytest -q tests/test_f10_reliability.py
python -m pytest -q
```

These are commands for a local run, not results of a run executed during documentation work. The repository's other domain suites remain necessary for complete GPX, DEM, temporal, Garmin schema and route-analysis coverage. Even full CI success does not replace separately collected physical-device field data.

## Operational limits

F10 does not add network/telemetry collection, device control, Garmin course export inspection, FIT generation, forced geometry decimation or automatic off-course testing. A physical field protocol already exists in [`docs/f10-field-validation.md`](../f10-field-validation.md). Use its offline, device-specific observation steps before asserting actual import, independent backup, navigation or alerts.
