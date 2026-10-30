# S01-CHR — Approved Preservation and Exclusion Verification

**Verification ID:** `S01-CHR-EXV-v1.0.0`  
**Functional contract:** `S01-CHR-v1.0.0` — approved/baselined, unchanged  
**Exclusion baseline:** `S01-SCOPE-EXC-v1.0.0` — approved/baselined, unchanged  
**Scope:** characterization admission, inventory, report generation, and installed CLI; **not** the separately permitted downstream F06/F07 production workflows.  
**Execution source:** `tests/test_s01_exclusion_contract.py`  

## 1. Negative-contract traceability

| ID | Approved traceability | Independently tested negative behavior | Evidence test |
|---|---|---|---|
| EXV-001 | EXC-001 / INV-001 | Input bytes remain identical, including comments, formatting and lexical precision; repeated results deterministic | `test_exv_001_source_bytes_unchanged` |
| EXV-002 | EXC-010 / INV-002 | Spatial spike retained; exact original point count and geographic extent | `test_exv_002_spatial_outliers_never_removed` |
| EXV-003 | EXC-005 / INV-003 | Non-monotonic source timestamps not reordered or reconstructed; no premature L3 quality verdict | `test_exv_003_temporal_regression_not_reordered` |
| EXV-004 | EXC-004 / INV-004 | Missing midpoint elevation and time remain missing; source point count unchanged | `test_exv_004_missing_observations_not_interpolated` |
| EXV-005 | EXC-006 / INV-003 | Two singleton segments do not become a line; multi-point segments retain distinct boundaries | `test_exv_005_segments_not_merged` (two variants) |
| EXV-006 | EXC-007 / INV-001 | Extreme source elevations preserved, vertical datum remains unknown | `test_exv_006_extreme_elevations_never_rewritten` |
| EXV-007 | EXC-003 / INV-005 | Opaque unknown extension retained byte-for-byte; only namespace/field inventory, no invented semantics | `test_exv_007_opaque_extensions_not_removed` |
| EXV-008 | EXC-013 / INV-010 | Installed `characterize` emits one JSON stdout report, without navigation/export artifacts or source modification | `test_exv_008_no_navigation_outputs` |
| EXV-009 | EXC-015 / INV-005 | Temporal/kinematic capability reported as eligibility only; no performance analytics or L3/L4 PASS | `test_exv_009_metrics_remain_diagnostic_only` |
| EXV-010 | INV-006 / INV-007 | Partial field coverage, unavailable time, unknown vertical reference, unverified privacy, and unknown origin remain explicit | `test_exv_010_uncertainty_and_missingness_explicit` |

The EXV-007 mapping above reproduces the previously approved identifier pairing; independent extension-preservation semantics are also governed by `S01-CHR-v1.0.0` CHR-06 and the approved non-destructive behavior. This verification change does not reinterpret or revise the exclusion baseline.

All ten scenarios independently construct synthetic GPX 1.1 XML fixtures and use the real `characterize_gpx` entrypoint. The common oracle checks exact file bytes, SHA-256, point inventory, report schema, and absence of replacement GPX. EXV-008 additionally exercises the installed subprocess interface; it is mandatory in the production CI environment and is **not silently skipped**.

## 2. Additional failure-path checks

`test_exclusion_failure_path_never_repairs_input` independently checks truncated XML and a coordinate outside the GPX 1.1 schema bounds. A failed admission must not produce a successful characterization, classification, or capability verdict; source bytes are unchanged and no sidecar output is written.

## 3. Evidence and acceptance

Acceptance requires:

1. Exactly one active, separately asserted EXV-001 through EXV-010 test group; EXV-005 runs two parameter variants.
2. Both negative failure-path variants pass.
3. GitHub Actions' full regression workflow succeeds for Python 3.11 and 3.12 on the PR head; the post-merge workflow remains a separate later check.
4. Existing F08 unregistered-extension **export** rejection behavior remains unchanged. The S01-CHR characterization path still inventories unknown well-formed extensions without treating them as trusted telemetry.
5. No runtime implementation, approved contract, schemas or existing validated test behavior is silently modified in this verification-only PR.

Only CI results on the actual repository checkout and bundled pinned GPX/Garmin schemas are accepted as repository verification evidence. Local smoke runs using simplified schemas are development feedback, **not** equivalent to full-schema results. Reports establish tested source preservation for the supplied fixtures; they do not certify arbitrary XML parser worst-case memory, empirical acquisition provenance, GNSS sensor accuracy, or full Stage 01 closure.

## 4. Execution evidence

**Awaiting CI**. Replace this section with the exact run URL, tested commit, job conclusions, and pytest counts once GitHub Actions completes. Tests are not presumed to have passed merely because their definitions exist.