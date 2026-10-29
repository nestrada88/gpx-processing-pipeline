# Numerical coverage assessment — consolidated NV-06 main

**Evidence:** GitHub Actions [run 40908624720](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40908624720), commit `cd3a4d3c9917f08929cdc8c45d3265312c64882a`, 2026-10-29. Read both job logs' pytest-cov `term-missing` tables; workflow uploaded `coverage.json` and `coverage.xml` in separate artifacts. The artifact JSON contents have **not** been independently decoded here. The statements below are transcript-grounded log measurements, not inferred file percentages.

## Measured regression outcome

| Measure | Python 3.11 | Python 3.12 |
|---|---:|---:|
| Job result | Success | Success |
| Tests passed | 415 | 415 |
| Total statements | 2390 | 2390 |
| Missing statements | 117 | 117 |
| Total branches | 860 | 860 |
| Missing branches | 94 | 94 |
| Combined statement/branch coverage (pytest-cov reported) | 93% | 93% |
| Warnings | 177 | 130 |

The 93% is **combined** coverage reported by pytest-cov, not a separately calculated statement-only or branch-only percentage. Use the archived JSON for exact individual percentages and missed arc locations.

## Numerical module coverage (identical in both jobs)

| Module | Statements | Miss | Branches | Partial/missed branches | Reported coverage |
|---|---:|---:|---:|---:|---:|
| spatial.py | 98 | 3 | 34 | 1 | 97% |
| dem.py | 126 | 9 | 56 | 7 | 90% |
| dem_sampling_adapter.py | 64 | 6 | 24 | 3 | 90% |
| terrain.py | 151 | 10 | 50 | 10 | 90% |
| terrain_sampling.py | 134 | 2 | 40 | 3 | 97% |
| temporal.py | 130 | 7 | 40 | 5 | 93% |
| analytical.py | 119 | 6 | 44 | 6 | 93% |
| route_analysis.py | 198 | 12 | 70 | 12 | 91% |
| activity_forecasting.py | 193 | 10 | 60 | 7 | 93% |
| planned_recorded.py | 182 | 14 | 74 | 13 | 89% |
| pipeline.py | 113 | 8 | 32 | 4 | 92% |

The `BrPart` column from pytest-cov is copied as a branch-gap count here, not interpreted as unexecuted independent code paths.

## Risk-ranked uncovered cases (source reviewed at the measured commit)

| Rank | Evidence | Gap and why it matters | Follow-up |
|---|---|---|---|
| **P1-A** | `dem_sampling_adapter.py:102,104,109-110,121` | Nonfinite/invalid coordinates, projection failure and DEM sampling error handling remain uncovered; incorrect conversion could undermine all elevation-dependent analytics | Synthetic invalid coordinate inputs and injected `ProjError`/raster errors; assert typed failure without publication |
| **P1-B** | `route_analysis.py:163,169,174,177,186,203,205,207,212` | Missing tests for noncontiguous identities, incomplete terrain/timing contracts, nonfinite heights, inconsistent speed×duration and missing timed edges | Dataclass mutation adversarial fixtures; assert fail-closed errors and no fabricated totals |
| **P1-C** | `terrain.py:107,109,122,127,146,156,164,181,219,228` | Upstream invalidity, sample mismatches, nonfinite heights, zero-distance handling and unsupported surface geometry | Boundary and invalid provenance/sample tests; ensure undefined grades remain unavailable |
| **P1-D** | `temporal.py:112-115,140,145,149,171` | Timestamp parser and invalid upstream spatial/distances remain unexercised under relevant conditions | Valid GPX chronology edge fixtures; distinguish naturally unreachable defenses requiring injected input |
| **P1-E** | `dem.py:86-87,104,107,163,175,177,179,208` | GPX route DEM samples and raster failure paths insufficiently exercised | Route fixture, malformed raster/transform, explicit fallback and exception tests |
| **P2-A** | `planned_recorded.py:123,129,132,140,146,159,197-200,231,275-276` | Edge-case comparison geometry, unmatched tracks, missing elevations and deviation grouping | Synthetic comparison fixtures; preserve unmatched or unknown results |
| **P2-B** | `activity_forecasting.py:143,145,156-157,190,204,226→228,279-285` | Forecast date overflow, invalid aggregate/edge combinations and ambiguous checkpoint paths | Explicit overflow/identity/uncertainty and checkpoint fixtures |
| **P2-C** | `pipeline.py:62,71,77,79,127-128,162,187` | Selected source/file errors and refusal-to-publish branches | Pipeline CLI/error-path tests asserting no partial publication |

**Classification note:** These are missing test executions at specific lines or arcs, not confirmed production defects. Determine whether each path is reachable through public inputs, unreachable defensive code, or requires fault injection before adding a regression test. No arbitrary minimum coverage threshold is set by this assessment.

## Interpretation and recommended next engineering work

1. Add targeted tests for **P1-A through P1-C** first. Treat nonfinite coordinates, datum/raster transformations, analytical consistency and terrain mismatch as failure-path priorities.
2. Test P1-D and P1-E next, distinguishing public-input reachability from injected upstream corruption.
3. Address P2 cases after critical handling has executable evidence. Re-run full Python 3.11/3.12 tests and compare exact `coverage.json` missing-line and missing-branch inventories at each new commit.
4. Assess 177 versus 130 warnings by category; at least one observed warning in both jobs is Rasterio's pending deprecation at `dem.py:105` related to affine multiplication. Warnings are not automatically test failures; avoid suppressing them without classification.
5. Coverage alone cannot establish geodetic truth, DEM measurement accuracy, or calibrated real-world pace. Physical Garmin field navigation evidence remains **on hold**.

## Reproduction

```sh
python -m pytest -q --cov=gpx_pipeline --cov-branch --cov-report=term-missing --cov-report=json:coverage.json
python scripts/numerical_coverage_report.py coverage.json --output numerical-coverage-summary.json
```

The summary is not presented as a newly executed local test run. All numeric results above were extracted directly from the successful GitHub Actions jobs.
