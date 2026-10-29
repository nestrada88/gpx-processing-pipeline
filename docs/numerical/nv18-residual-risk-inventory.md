# NV-18 — Residual Risk Inventory

## 1. Scope, provenance, and reproducibility

- Repository: `nestrada88/gpx-processing-pipeline`
- Immutable examined baseline: `b799bcf4a260b40ef93c16b4c89798b095ab31fe` (NV-17, PR #60, merged).
- Post-merge workflow: [Full regression and coverage verification #40915978247](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40915978247), completed successfully for Python 3.11 and 3.12.
- Per-environment result: **478 passing tests**; **2,390 executable statements, 57 missed; 860 branch opportunities, 49 partially covered; 97% rounded combined coverage**.
- Evidence: per-module `term-missing` output in CI logs, reviewed at the immutable source commit; CI generated two `coverage-python-3.11` / `coverage-python-3.12` artifacts. Classification below is **source-level triage**, **not a line-by-line proof of reachability**. The artifact archive's detailed arcs were not decoded, so branch targets beyond those printed are not asserted.
- Coverage display's `BrPart` counts represent **partial branches**, not necessarily a count of every missing arc. Do not equate 49 to 49 distinct untested branch destinations.
- No external device, raster corpus, instrument calibration, production fixes, or hardware field test was performed in NV-18.

### Classification rules

| Label | Interpretation | Follow-up |
|---|---|---|
| R1 | Plausibly reachable consequential input/dependency failure; correctness, integrity or user-visible contract at risk | Reproduce with a realistic fixture/fault; test, fix only if defect demonstrated |
| R2 | Defensive internal contract or exceptional environment case; may require controlled fault injection | Retain with justification; test selectively |
| R3 | Likely dominated by an earlier validation/invariant or platform branch unreachable on the current runner; **provisional until confirmed** | Document call graph/guards, avoid fake integration tests |
| R4 | Measurement/model uncertainty not resolved by statement/branch coverage | Validate independently with reference data and stated error bounds |

Severity labels: **P1** consequential output/source/navigation integrity, **P2** failure classification or supported scientific edge case, **P3** low-consequence/internal redundancy. They express triage priority, not confirmed defects.

## 2. Complete module-level coverage register

All 22 modules printed by the NV-17 post-merge report are included. The **57 missed statements and 49 partially covered branches** reconcile to the CI totals. Locations are immutable NV-17 source line numbers, not yet guaranteed after further edits.

| Module | Stmts missed | Partial branches | Reported uncovered locations | Preliminary risk and disposition |
|---|---:|---:|---|---|
| `__init__.py` | 0 | 0 | — | Covered |
| `activity_forecasting.py` | 2 | 3 | 190, 204, 226→228 | R3/P3: F06 `analyze_route` dominates point identity/finite edge checks; verify no mutation bypass. Branch around `seconds is not None` overlaps explicit grade-unavailable path; inspect arc before further tests |
| `analytical.py` | 2 | 2 | 154, 156 | R2/P2: injected inconsistent F03 terrain profile / F04 temporal edge counts must fail closed; integration reachability depends on producing valid upstream module output |
| `cli.py` | 9 | 4 | 80, 89–94, 102, 109 | R1/P2: `--debug`, fallback error and human validate text; `__main__` entry-point coverage requires subprocess; test exit status / stderr without changing semantics |
| `dem.py` | 3 | 3 | 104, 107, 179 | R1/P2: nonfinite projected sampling coordinates or degenerate raster affine; distinguish input transform failures from physical elevation accuracy |
| `dem_sampling_adapter.py` | 2 | 1 | 75, 121 | R1/P2: degenerate affine and raster/Proj I/O exceptions; fail closed and preserve coordinate semantics |
| `field_evidence.py` | 0 | 0 | — | Covered; neither device field fidelity nor actual navigation verified by coverage |
| `garmin_compatibility.py` | 5 | 6 | 48, 134, 209, 214→213, 262, 284 | R1/P1: extension schema absence, header/geometry audit mismatch and checkpoint order validation; some branches involve injected malformed exporter metadata |
| `garmin_export.py` | 5 | 5 | 166, 192→190, 215→208, 270–271, 275, 277 | R1/P1: unsupported XML nodes/extensions, XSD rejection, geometry mutation or invalid export spatial verdict; distinguish upstream guard domination |
| `interoperability.py` | 2 | 2 | 97, 128 | R1/P1: unresolved XML entity security boundary and non-element XML nodes in extension validation; parser configuration can make entity branch unreachable, document explicitly |
| `operational_verification.py` | 0 | 0 | — | Covered; not hardware verification |
| `output.py` | 5 | 1 | 53–54, 66–69 | R1/P1: Linux missing `renameat2`, Windows publication path and unsupported platform. **Windows `rename` must be assessed for no-replace atomicity**; Linux CI alone does not establish cross-platform behavior |
| `pipeline.py` | 2 | 2 | 162, 187 | R1/P1: incompatible Garmin software verdict must block publication; R2/P3: `NO_OUTPUT` guard may be unreachable for validated commands |
| `pipeline_config.py` | 1 | 1 | 44 | R2/P3: reject adaptive sampling on unsupported command; direct config boundary |
| `planned_recorded.py` | 4 | 6 | 123, 129, 132, 244, 310→312, 312→314 | R2/P2: geometry point identity/coordinate fallback largely dominated by F06 validation; R1/P2: route-vs-track filtering, planned/recorded duration diagnostics and rejoin events deserve semantic fixtures |
| `production_schemas.py` | 2 | 3 | 120, 130→138, 137 | R1/P1: malformed placement of extension XML must be rejected, namespace-bearing comments/non-elements should be safely skipped |
| `route_analysis.py` | 1 | 1 | 284 | R2/P3: unaccounted canonical point record fallback; likely dominated by earlier explicit point/segment invariants, verify call graph |
| `spatial.py` | 3 | 1 | 94, 111–112 | R1/P2: absent lat/lon and malformed elevation in direct spatial parser, possibly rejected earlier by GPX schema/parser; preserve typed errors |
| `temporal.py` | 3 | 1 | 112–113, 115 | R1/P2: invalid ISO timestamps and timezone-naive timestamps, possibly blocked by GPX XSD/parser; separate direct-unit vs end-to-end behavior |
| `terrain.py` | 3 | 3 | 164, 219, 228 | R1/P2: nonfinite DEM sample, unsupported raster band/CRS, rotated/degenerate raster, all must fail closed without invented height/grade |
| `terrain_sampling.py` | 2 | 3 | 111, 113, 179→183 | R1/P2: invalid elevation callback/source description; empty-segment behavior and adaptive sampling source identity |
| `waypoints.py` | 1 | 1 | 97 | R2/P3: noncallable reverse geocoder direct contract |
| **TOTAL** | **57** | **49** | | **CI reconciled** |

## 3. Prioritized executable risk register

| ID | Priority | Impact / boundary | Evidence | Next verification and exit observation |
|---|---|---|---|---|
| NV18-R01 | P1 | Exported Garmin GPX geometry, XSD and audit integrity | `garmin_export.py:270–277`; `garmin_compatibility.py:262,284`; pipeline:162 | Corrupt exported serialization/audit using a scoped deterministic mock, verify no publish and a specific diagnostic; genuine supported export must retain source point order and coordinates |
| NV18-R02 | P1 | XML extension structural/security correctness | `interoperability.py:97,128`, `production_schemas.py:120,130,137`, `garmin_export.py:166,192`, `garmin_compatibility.py:209,214` | Exercise valid vs invalid namespaces and extension placements, comments and unresolved-entity parser behavior; rejected payload must never silently lose unknown data |
| NV18-R03 | P1 | Atomic no-replace output semantics across platforms | `output.py:53–54,66–69` | Verify Linux fallback when `renameat2` is missing; inspect/verify Windows target-already-exists behavior and filesystem atomicity. Do not infer Windows safety from Linux CI |
| NV18-R04 | P2 | DEM projection / affine and sampler exceptional inputs | `dem.py:104,107,179`, `dem_sampling_adapter.py:75,121` | Synthetic degenerate/invalid affine and nonfinite transform outputs; reject with explicit cause, preserve horizontal/vertical datum provenance; run independent reference-raster cases |
| NV18-R05 | P2 | Terrain sampling no fabricated elevations | `terrain.py:164,219,228`; `terrain_sampling.py:111,113,179→183` | Exercise raster geometry, callback type, empty segments, nonfinite height; check null propagation and source geometry immutability |
| NV18-R06 | P2 | Error classification at CLI and direct parsers | `cli.py:80,89–94,102,109`; `spatial.py:94,111`; `temporal.py:112–115` | Subprocess CLI tests and direct parsing tests, with expected typed errors/exit codes; characterize parser-dominated cases rather than bypassing all guards |
| NV18-R07 | P2 | Comparison diagnostics and rejoin semantics | `planned_recorded.py:244,310→314` | Use route-only recorded input, absent/available observed duration, multi-fix departure/rejoin; ensure recorded timestamps are never replaced by forecast time |
| NV18-R08 | P2 | Upstream analytical array consistency | `analytical.py:154,156`; `activity_forecasting.py:190,204` | Fault-injection tests of F03/F04 array shapes only if they identify a meaningful contract; independent validated producers are already covered |
| NV18-R09 | P3 | Redundant/guard-dominated contract branches | `route_analysis.py:284`; `planned_recorded.py:123,129,132`; `pipeline.py:187`; `pipeline_config.py:44`; `waypoints.py:97` | Show reachable caller paths or documented earlier rejection. Do not increase coverage using arbitrary mutation that contradicts public invariants unless it demonstrates fail-closed behavior |
| NV18-R10 | R4 | Physical representativeness of geodesic interpolation, DEM resolution and timing models | None can be closed by coverage alone | Compare known WGS84 numerical oracles, datum-consistent surveyed DEM references, and recorded timing/pace data with explicit tolerances, uncertainty, provenance and sampling sensitivity |

**Finding:** R01–R03 are the highest consequence because they affect exported field-navigation integrity or output publication. Their uncovered lines are **risk indicators, not demonstrated production defects**. R04–R07 are useful targeted test areas. R08–R09 should be considered only after demonstrating meaningful reachability. R10 is a distinct evidence obligation.

## 4. Verification boundaries and scientific constraints

1. **Geometry:** original GPX track/route vertex identity, order and segment boundaries are authoritative; adaptive geodesic densification cannot reconstruct actual path bends or imply trail surveying.
2. **Elevation:** DEM samples are not source GPS measurements; missing heights must remain missing; no vertical datum conversion without a defined transformation and appropriate grid/uncertainty provenance.
3. **Timing:** recorded timestamps are observations, forecast timestamps are model outputs; forecasts must not overwrite recorded time. Estimated arrival times depend on grade coverage, scenario assumptions and rests.
4. **Comparison:** planned vs recorded deviation is measured against fixed planned geometry, not fabricated connecting edges; off-course/rejoin semantics depend on sampled recorded fixes and configured tolerance.
5. **Outputs:** source file is immutable, rejected inputs/exports must not leave published partial artifacts; collision/no-replace is an operating-system and filesystem contract.
6. **Garmin:** static GPX/XSD and software compatibility checks do **not** verify on-device routing, alerts, turn guidance or import geometry. eTrex SE and Instinct 2X physical verification remains on hold.

## 5. Next technical sequence

**NV-18 outcome:** The inventory is complete at the **module-level term-missing granularity** and each uncovered source location is assigned to a risk workstream. It is not a proof that every missing arc is structurally unreachable, nor does it certify numerical correctness.

1. **NV-19A — Export and publication integrity (P1):** test or repair R01–R03 only where supported reproducible evidence shows consequential gaps. Prefer software-only Garmin export and atomic publication tests before device testing.
2. **NV-19B — Geodetic and temporal edge contracts (P2):** only if R04–R07 retain meaningful reachable gaps after inspection.
3. **NV-20 — Consolidated numerical verification:** link CI logs, source SHAs, independent oracles, realistic DEM tests, uncertainty and unresolved R4 limitations; do not equate 97% with correctness.
4. If the goal is true **per-arc exhaustive inventory**, first extract both detailed `coverage.json` artifacts and inspect their missing arc pairs; this report makes no claim to have done so.

## 6. Repository scope and change record

- Branch: `docs/nv18-residual-risk-inventory`, based exactly on NV-17 merge SHA.
- Files changed: this document only. No numerical algorithms, CI configuration, device exports or project workflow changed.
- No approvals/governance procedures, assigned review roles, or hardware verification implied.
