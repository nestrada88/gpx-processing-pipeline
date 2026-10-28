# F10 — Operational Reliability and Field Validation

## Responsibility and evidence boundaries

F10 distinguishes **pre-transfer software readiness**, **repeatable software reliability checks**, and **observed physical Garmin behavior**. Passing GPX parsing, XSD validation, F07 compatibility or F10 readiness is not proof that Garmin Explore/Connect imports a source faithfully, that the device preserves the course, that navigation alerts work, or that the primary/secondary devices can navigate independently offline.

Implementation: [PR #22 — F10](https://github.com/nestrada88/gpx-processing-pipeline/pull/22). Sources: [`operational_verification.py`](../src/gpx_pipeline/operational_verification.py), [`field_evidence.py`](../src/gpx_pipeline/field_evidence.py), F09 [`pipeline.py`](../src/gpx_pipeline/pipeline.py), and [`test_f10_reliability.py`](../tests/test_f10_reliability.py).

## Domain documentation

- [Device readiness](f10/device-readiness.md) — device-specific capacity gates, findings, F09 behavior and limitations.
- [Field evidence contract](f10/field-evidence-contract.md) — immutable observations, SHA-256 association, firmware/workflow identifiers and reproducible JSON.
- [Reliability verification](f10/reliability-verification.md) — regression evidence, boundaries, fault injection, numerical reference and reproduction.
- [Existing manual field-validation procedure](f10-field-validation.md) — separate steps for real Garmin import, geometry, alerts and offline operation. **Procedure present does not mean procedure executed.**

## Architectural data flow

```text
F01/F02/F08 source validation + F07 device-labeled GPX
                        |
                 F09 export/process
                        |
           F10 verify_device_readiness
               /                  \
       software-compatible?     explicit missing
       known constraints        physical evidence
               |
       F09 publishes operational report only if
       mandatory export checks did not fail

Manual device test (separate from CLI) -> FieldEvidenceRecord
  firmware + transfer workflow + source/export SHA-256 + observations
```

`verify_device_readiness` performs a deterministic *pre-transfer* check and returns `OperationalReadiness`. F09 emits one `verification/<device>-operational.json` per requested target, and aborts publication on known device-capacity errors. It does **not** build or populate `FieldEvidenceRecord`: these are separate explicitly supplied observations.

## Device capability distinction

| Constraint | Garmin eTrex SE | Garmin Instinct 2X Solar Tactical |
| --- | --- | --- |
| F10 per-course points | 200, conservatively enforced | No reliable fixed numeric limit encoded |
| F10 stored courses | 50, conservatively enforced | Not asserted |
| GPX source line handling | Each source track/route counted as one candidate course; track segments summed per track | No eTrex numerical limits applied |
| Actual import/converted geometry | Unverified until observed | Unverified until observed |
| Physical transfer/navigation | Always false in the software result | Always false in the software result |

The 200-point and 50-course eTrex constraints are **device-course** restrictions and differ from the **Explore website import-mode** ceilings documented by F07 (10,000 points per imported line for website import-as-tracks, 200 for import-as-routes, 500 waypoints per website import). The earlier F07 export profile's 1,000-waypoint device value is a separate constraint. See [F07 documentation](F07-GARMIN-NAVIGATION-EXPORT.md).

The official eTrex course constraint cited in the existing procedure is: https://support.garmin.com/da-DK/?faq=Hg2pM7ov4oAql6IzzaB398 . A pre-transfer point-count pass does not imply one-to-one import mapping after Garmin conversion.

## Source integrity and operational invariants

1. Never silently decimate, densify or reroute the source GPX to fit Garmin limits. F06 analytical processing remains independent and accessible even for GPX geometry exceeding eTrex course capacity.
2. Separate software `software_compatible` from `physical_transfer_verified` and `physical_navigation_verified`. The latter are set to `False` by `verify_device_readiness`, regardless of software status.
3. Unknown numerical limits, ambiguous multi-segment conversions and absent field evidence produce explicit `unverified` findings, not fabricated compatibility guarantees.
4. A field observation with `passed` or `failed` must cite an evidence reference and must identify a specific firmware, workflow, source digest and exported digest. The JSON record validates stated metadata, not the authenticity of the real-world observation.
5. F09 publishing uses staged files, SHA-256 checks and no-overwrite behavior; fault injection exercises particular failures and cannot certify recovery from all system, storage or power-loss faults.
6. WGS84 test references provide limited numerical regression evidence, not exhaustive geodesic, DEM or field certification.

## Verification state

Source implementations and [F10 tests](../tests/test_f10_reliability.py) are present; [PR #22](https://github.com/nestrada88/gpx-processing-pipeline/pull/22) was merged. This documentation-only delivery does **not** run tests, transfer any GPX to Garmin hardware, or record human observations. Consult CI independently, and execute the [existing manual procedure](f10-field-validation.md) to collect actual field evidence. All F10 interfaces should be imported from their implementation modules; the inspected package `__init__.py` does not currently re-export them.
