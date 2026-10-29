# NV-06 — Consolidated numerical regression evidence

## Repository integration traceability

The numerical verification sequence has been implemented in the following GitHub PRs:

| Phase | PR | Responsibility |
|---|---|---|
| NV-00 | #43 | Numerical inventory and test-reference map |
| NV-01 | #44 | WGS 84 geodesic reference and segment invariants |
| NV-02 | #45 | DEM arithmetic and datum declaration integrity |
| NV-03 | #46 | Terrain reference surfaces, ascent/descent and sampling limits |
| NV-04 | #47 | Temporal, kinematic and Tobler-model reference cases |
| NV-05 | #48 | End-to-end numerical and artifact consistency |
| NV-06 | Current PR | Regression coverage interpretation and reproducible evidence |

NV-05 merge baseline: `69bfc00f0728bde26197017bd0edbf020eded049`.

## Full regression command

```sh
python -m pip install -e '.[test]'
python -m pytest -q --cov=gpx_pipeline --cov-branch \
  --cov-report=term-missing --cov-report=xml:coverage.xml \
  --cov-report=json:coverage.json
python scripts/numerical_coverage_report.py coverage.json \
  --output numerical-coverage-summary.json
```

The repository's GitHub Actions workflow executes full regression with statement and branch coverage for Python 3.11 and 3.12. Each run must be tied to its **exact head SHA**. The summary script records actual coverage totals and per-module missing statements/branches, without inventing percentages or changing the underlying report.

## Verification record format

For each relevant GitHub Actions run, record:

- Commit SHA, workflow run ID and both Python job conclusions.
- `coverage.json`-derived coverage totals and numerical-module summaries, including uncovered statements and branches.
- Identified correctness-critical uncovered paths and regression follow-ups, if any.
- Independent geodesic, terrain and kinematic reference results from NV-01 through NV-05.
- Source-immutability, missing-DEM, multi-segment and manifest-integrity checks.

Successful CI verifies the automated suite executed successfully, **not** complete numerical proof, absolute terrain correctness or Garmin device operation. No arbitrary numeric coverage floor is introduced in NV-06; assess risk in the uncovered branches before selecting one.

## Known limits preserved

- Vertical datum labels are metadata assertions, not automated geodetic vertical transformations.
- Raw DEM ascent/descent depends on sampling and elevation noise.
- Adaptive geodesic interpolation does not reconstruct unobserved trail geometry.
- Tobler forecasts are explicit model-based estimates, not calibrated real-world ETA intervals.
- Physical Garmin field navigation verification (P0) remains on hold.

## Evidence state

NV-00 through NV-05 PR history is established, but **NV-06 CI must run on its own final commit**. Numerical coverage percentages are not stated here because coverage artifact JSON has not been read and assessed in this execution. The result of the pending CI run must be inspected before marking NV-06 regression complete.
