# NV-20 — Consolidated Numerical Verification Evidence and Limitations

## Scope and source authority

- Repository: `nestrada88/gpx-processing-pipeline`.
- Immutable baseline: `main` at `1e95bedee41f3bb5b5841b52135995aa3da8448f`, NV-19C PR #64 merge.
- Source of evidence: CI logs and checked-in regression tests; no new production changes or numerical experiments in NV-20.
- Evidence horizon: NV-00–NV-19C, with risk assessment NV-18 and targeted remediation tests NV-19A/B/C.
- This report records **software regression evidence**, **not** a certification of measurement accuracy, device compatibility, or scientific model validity.

## 1. CI status and numerical coverage

| Verification point | GitHub evidence | Tests per Python version | Combined coverage | Missed statements | Partial branches |
|---|---|---:|---:|---:|---:|
| NV-06 | [PR #49](https://github.com/nestrada88/gpx-processing-pipeline/pull/49) | 415 | 93% | 117 | 94 |
| NV-10 | [PR #53](https://github.com/nestrada88/gpx-processing-pipeline/pull/53) | 442 | 95% | 87 | 69 |
| NV-13 | [PR #56](https://github.com/nestrada88/gpx-processing-pipeline/pull/56) | 460 | 96% | 73 | 60 |
| NV-17 | [post-merge run #40915978247](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40915978247) | 478 | 97% | 57 | 49 |
| NV-19A | [PR #62](https://github.com/nestrada88/gpx-processing-pipeline/pull/62) | 483 | 97% | 55 | 47 |
| NV-19B | [PR #63](https://github.com/nestrada88/gpx-processing-pipeline/pull/63) | 487 | 97% | 50 | 46 |
| **NV-19C** | [post-merge run #40921192680](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40921192680) | **497** | **97%** | **45** | **43** |

The NV-19C branch run [#40921065318](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40921065318) passed on Python 3.11 and 3.12. Its `term-missing` report printed 2,390 statements (45 missed), 860 branches (43 partial), and 97% combined coverage. The post-merge `main` run #40921192680 completed successfully. The counts above originate from branch CI rather than an independently decoded `coverage.json` arc inventory; **partial branch count is not an exhaustive catalog of missing directed arcs**. The scope of this report does not imply exact per-arc proof of reachability.

## 2. Domain-specific results and evidence boundaries

| Responsibility | Evidence achieved | Not established |
|---|---|---|
| WGS84 spatial distances, segment boundaries | Independent geodesic regressions; invalid source geometry is rejected; no connecting edges fabricated | Real-world trail centerline accuracy and GNSS uncertainty |
| DEM sampling and vertical datum | Raster transform, no-data, grade/height boundary regressions; incompatible datums do not produce numeric elevation comparison | Elevation ground truth, grid transformation accuracy and vertical uncertainty |
| Terrain and adaptive geodesic samples | Gradient, ascent/descent, missing data, corrupted F02 interfaces and invalid callbacks tested | Curved trail reconstruction from sparse GPX vertices; geodesic densification is not surveyed path geometry |
| Temporal and kinematic | Observed chronology and impossible calendar date rejection; missing times not simulated as observations | Device timestamp precision and recorded-field pace representativeness |
| Forecasting / checkpoint ETA | Scenarios, model bounds, missing grade, overflow, checkpoint identity and rest semantics | Forecast accuracy against actual hiking times or physiological conditions |
| Planned vs recorded | Deviation, rejoin, reference-edge boundaries, DEM midpoint and vertical datum compatibility | Sampling sensitivity, GPS positional uncertainty and observed-course fidelity |
| Garmin export and transfer | Static geometry/waypoint hashing, re-signed tampering, audit/header/namespace/workflow incompatibility checks | Explore/Connect conversion fidelity, actual eTrex SE and Instinct 2X behavior |
| Publication | Linux native no-replace collision checks; staging failure, hash readback, `fsync`, simulated Windows collision and unsupported-platform fail-closed tests; `output.py` reached 100% coverage | Native Windows filesystem behavior, network filesystem guarantees, power-loss durability |

## 3. Remaining uncovered source-location inventory

All **45** missed statements and **43** partial branches reconcile to CI's NV-19C `term-missing` report. Missing source location numbers below refer to the exact baseline commit. The reported `BrPart` column measures partially covered branches, not a complete list of branch arcs.

| Python module | Missed statements | Partial branches | Remaining source locations / selected arcs |
|---|---:|---:|---|
| `__init__.py` | 0 | 0 | — |
| `activity_forecasting.py` | 2 | 3 | 190, 204, 226→228 |
| `analytical.py` | 2 | 2 | 154, 156 |
| `cli.py` | 9 | 4 | 80, 89–94, 102, 109 |
| `dem.py` | 2 | 2 | 107, 179 |
| `dem_sampling_adapter.py` | 2 | 1 | 75, 121 |
| `field_evidence.py` | 0 | 0 | — |
| `garmin_compatibility.py` | 3 | 4 | 48, 134, 209, 214→213 |
| `garmin_export.py` | 5 | 5 | 166, 192→190, 215→208, 270–271, 275, 277 |
| `interoperability.py` | 2 | 2 | 97, 128 |
| `operational_verification.py` | 0 | 0 | — |
| `output.py` | 0 | 0 | — |
| `pipeline.py` | 2 | 2 | 162, 187 |
| `pipeline_config.py` | 1 | 1 | 44 |
| `planned_recorded.py` | 4 | 6 | 123, 129, 132, 244, 310→312, 312→314 |
| `production_schemas.py` | 2 | 3 | 120, 130→138, 137 |
| `route_analysis.py` | 1 | 1 | 284 |
| `spatial.py` | 3 | 1 | 94, 111–112 |
| `temporal.py` | 1 | 1 | 115 |
| `terrain.py` | 3 | 3 | 164, 219, 228 |
| `terrain_sampling.py` | 0 | 1 | 179→183 |
| `waypoints.py` | 1 | 1 | 97 |
| **TOTAL** | **45** | **43** | |

## 4. Residual risk and disposition

This report updates the risk-based [NV-18 inventory](nv18-residual-risk-inventory.md). A missed line is a triage signal, not a demonstrated defect. Do not claim any untested defensive guard is provably unreachable until its caller/validation dominance is established.

| Residual class | Impact | Disposition |
|---|---|---|
| **P1 — Garmin navigation export** | `garmin_export.py`, `garmin_compatibility.py`, `pipeline.py` retain exceptional integrity paths | Add realistic negative integration tests only if actionable; software verification is distinct from physical-device validation |
| **P1 — XML/extension security** | `interoperability.py`, `production_schemas.py` retain entity/extension structural branches | Establish parser reachability and local authoritative XSD behavior; do not relax unknown extension rejection |
| **P1 — Native Windows output publication** | Native platform behavior unverified despite full Linux coverage and simulated collision checks | Test Windows and filesystem semantics on native environment before advertising cross-platform atomicity |
| **P2 — DEM and terrain** | Degenerate raster/transformed coordinates, nonfinite height defenses | Build source-preserving reference fixtures; do not invent heights or datum transforms |
| **P2 — CLI and temporal error paths** | CLI `--debug`, generic error mapping; direct malformed timestamps | Exercise supported public entrypoints where consequential, preserve typed failure behavior |
| **P2 — Comparison diagnostics** | Some route-only and timing/rejoin cases remain unexercised | Verify diagnostic semantics from recorded timestamps, not forecast substitutions |
| **P3 — Guard-dominated internals** | F02/F03/F04/F06 structural fallbacks and `NO_OUTPUT` sentinel | Demonstrate invariant domination before removing or testing purely for percentage gain |
| **R4 — Scientific external validity** | DEM resolution/datum bias, sparse geometry, motion model and GPS noise | Needs independent external ground truth, published numerical oracles and uncertainty budgets |

## 5. Explicit numerical invariants

1. Original GPX coordinate tokens, track/route boundaries, waypoint identity and order remain immutable across analytics and export.
2. F02 WGS84 geodesic distances and independent segment topology take precedence over guidance/course interpretations.
3. DEM elevation is a derived measurement with explicit provenance. A missing sample is not a zero; datum mismatch prohibits arithmetic comparison.
4. Recorded timestamps are observations. Forecast durations and ETAs remain modeled outputs and are never substituted for recorded time.
5. Output is staged, integrity-checked and published without replacing an existing target on verified platforms; publication errors leave no success-looking partial result.
6. Garmin GPX validation is not a physical navigation verification. Source-to-device transformations through Garmin Explore/Connect remain unverified.

## 6. Final disposition and follow-on

**Software numerical regression phase: consolidated evidence complete, with listed limits.** 497 passing tests per Python environment and 97% combined coverage support a robust regression baseline, **not** proof of all numerical correctness or field-readiness.

- Retain NV-18 classifications for uncovered branches; close no R1/P1 risks solely on coverage.
- Prioritize native OS collision semantics, Garmin software conversion, geodetically accurate reference-raster validation and measured pace/ETA error before declaring field-readiness.
- If continued internal hardening is valuable, start only a specific, reproduced risk-driven test/fix instead of iterating branches toward 100% coverage.
- P0 physical Garmin eTrex SE and Instinct 2X field verification remains explicitly **on hold**.

## 7. Reproduction and traceability

```bash
python -m pytest -q --cov=gpx_pipeline --cov-branch --cov-report=term-missing
```

Tests also run via GitHub Actions on Python 3.11 and 3.12. Results here are grounded in NV-19C branch and post-merge workflows, not in a new NV-20 numerical test execution.

Repository change: **documentation only**, based on immutable NV-19C merge. No code changes, no project governance/approval workflow, no physical device assertions.
