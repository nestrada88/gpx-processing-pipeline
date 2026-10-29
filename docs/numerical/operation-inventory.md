# NV-00 — Numerical verification baseline and operation inventory

Repository baseline: `main` commit `e5adbc1656b0a4540fc0fab4487dd12501fbb2a0` (2026-10-29).
Scope: F02, F03, F04, F06 and their numerical dependencies. Garmin physical field validation is excluded.

## Evidence and reproducibility

- GitHub Actions workflow: `.github/workflows/f01-f03-tests.yml`; run [40815704410](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40815704410) passed for Python 3.11 and 3.12 at the baseline SHA.
- Two coverage artifacts were uploaded: `coverage-python-3.11` and `coverage-python-3.12`.
- **Coverage percentages and missed-line/branch counts have not been extracted or evaluated in this inventory.** Successful jobs and existence of artifacts do not imply a coverage threshold, mathematical proof, or device readiness.
- Reproduce locally:

```sh
python -m pip install -e '.[test]'
python -m pytest -q --cov=gpx_pipeline --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json \
  --cov-report=xml:coverage.xml
```

- Record Python, GeographicLib, Rasterio, PROJ/pyproj, NumPy and GDAL versions with each subsequent numerical comparison; keep the reference fixture and tolerance definition alongside the test.
- This inventory is a function-level traceability baseline, **not** evidence that independent numerical oracles have passed.

## Calculation inventory

| ID | Domain | Source / public operation | Inputs and reference | Output / numerical semantics | Existing test entrypoints | Verification still required |
|---|---|---|---|---|---|---|
| NV01-01 | F02 | `spatial.geodesic_distance_m` | WGS 84 lat/lon degrees; GeographicLib WGS84 inverse | Ellipsoidal horizontal distance, metres | `test_f02_spatial.py`, F03/F06 hardening tests | Independently fixed distance references; antimeridian/polar cases; symmetry, zero, finite bounds |
| NV01-02 | F02 | `spatial.validate_spatial` | GPX tracks, track segments, routes and waypoints | Per-segment consecutive edge-distance tuples; validation findings; invalid edges represented by NaN | `test_f02_spatial.py` | Multi-segment invariants, no implicit joins, input unchanged |
| NV01-03 | F06 | `route_analysis.analyze_route` | Canonical analytical dataset, source segment distances | Segment and route statistics, metres | `test_f06_route_analysis.py`, `test_f03_f06_numerical_terrain_hardening.py` | Independent total-distance references and cross-domain reconciliation |
| NV01-04 | F06 | `terrain_sampling.terrain_adaptive_sample` | Original WGS 84 vertices, DEM callback, spacing/residual budgets | Geodesically interpolated analytical locations, not observed trail geometry | `test_terrain_sampling.py`, `test_dem_sampling_adapter.py` | Endpoint identity, antimeridian, spacing/depth/budget behavior |
| NV02-01 | F03 | `dem._sample` / `dem.enrich_dem` | Single-band raster, horizontal CRS, pixel transform, metre elevations | Optional nearest/bilinear DEM values; explicit unavailable status | `test_f03_dem.py`, `test_f03_f06_numerical_terrain_hardening.py` | Known analytical planes, edge pixels, masks, NoData and fractional coordinates |
| NV02-02 | F03/F06 | `dem_sampling_adapter.sample_terrain_from_dem` | WGS 84 input to raster CRS via pyproj; local DEM | Adaptive derived samples and provenance; no vertical conversion | `test_dem_sampling_adapter.py`, F03/F06 hardening tests | CRS transformation oracle; vertical datum compatibility and missing datum semantics |
| NV03-01 | F03 | `terrain.analyze_terrain` | Segment edge distances and point-indexed DEM heights, metres | Raw ascent/descent, min/max/mean and grade, with incomplete coverage | `test_f03_terrain.py` | Synthetic monotonic and oscillating surfaces; zero-length edge; noise sensitivity |
| NV03-02 | F03 | `terrain.analyze_dem_surface` | Orthogonal metric projected raster and odd neighborhood | Horn 3x3 central slope, degrees; window relief, metres | `test_f03_terrain.py`, terrain hardening tests | Constant/linear plane and orientation; masked-cell and edge-window cases |
| NV03-03 | F06 | `terrain_sampling.terrain_adaptive_sample` | DEM curvature residual, spacing and recursion budget | Segment-safe adaptive density; diagnostics on unsatisfied resolution | `test_terrain_sampling.py`, `test_f03_f06_terrain_analytical_consistency.py` | Bounded termination, refinement residual and coverage guarantees |
| NV04-01 | F04 | `temporal.analyze_temporal` | Source timestamps with offsets; F02 horizontal distances | Elapsed seconds, speed m/s, anomaly findings; segment boundaries | `test_f04_temporal.py` | Zero/reversed times, offset equivalence, missing time, overflow |
| NV04-02 | F06 | `activity_forecasting.tobler_speed_kmh` | Grade and model constants | Tobler-model walking speed, km/h | `test_f06_activity_forecasting.py` | Independently computed model reference cases and units |
| NV04-03 | F06 | `activity_forecasting.forecast_activity` | Analytical geometry, optional grade, scenario settings | Modeled duration, checkpoint ETA and scenarios; not observed duration | `test_f06_activity_forecasting.py` | Monotonic ETA, missing grade semantics and scenario ordering |
| NV05-01 | F06 | `analytical.build_analytical_dataset` | GPX, optional DEM and waypoint catalog; temporal processing | Canonical immutable source-linked point/segment rows | `test_f06_analytical.py` | Independent segment totals, source hash and no synthetic observations |
| NV05-02 | F06 | `planned_recorded.compare_planned_recorded` | Two separately validated analytical datasets | Route comparison metrics | `test_f06_planned_recorded.py` | Identity, reversals, nonmatching lengths, partial coverage |
| NV05-03 | F09 | `pipeline.run_pipeline` | Parsed GPX, DEM and explicitly selected features | Published JSON reports with input/output hashes | `test_f09_pipeline.py`, integration tests | Repeated-run semantic equivalence and cross-report consistency |

## Reference fixture matrix for subsequent NV branches

The following cases identify missing **independent-oracle evidence**, not assertions that each case is currently untested:

| Fixture | Expected relationship / oracle | Owner |
|---|---|---|
| Coincident WGS 84 points | Zero horizontal distance | NV-01 |
| Antimeridian and polar geodesics | Trusted externally fixed WGS 84 solution; never the same implementation call as expected value | NV-01 |
| Two separated track segments | Total equals within-segment edges, with no connecting displacement | NV-01 / NV-05 |
| Synthetic affine DEM: constant/linear plane | Analytical nearest/bilinear height and slope reference | NV-02 / NV-03 |
| Synthetic DEM with NoData cells | Undefined outputs remain unavailable; no implicit zero elevation | NV-02 / NV-03 |
| Conflicting or absent vertical datum | Explicit compatibility failure or unresolved datum state; no silent equivalence | NV-02 |
| Flat/monotonic/oscillating elevations | Exact raw ascent/descent; quantify noise sensitivity separately | NV-03 |
| Adaptive interval at max-depth/min-spacing | Termination and explicit `SAMPLING_RESOLUTION_LIMIT` where necessary | NV-03 |
| Same UTC time with different explicit offsets | Equivalent duration and ordering | NV-04 |
| Zero/reverse time edge | No invented finite speed | NV-04 |
| Fixed Tobler grade | Independent equation reference, units and scenario bounds | NV-04 |
| Full analyze vs process run on same GPX/DEM | Equal common numerical fields and source fingerprint | NV-05 |

## Numerical contract template (apply per NV test)

```text
ID:
Function and module:
Reference source / oracle and fixture hash:
Inputs; coordinate reference; vertical reference; units:
Expected result / mathematical invariant:
Absolute tolerance (units):
Relative tolerance (dimensionless):
Boundary and missing-data behavior:
Diagnostic code / severity where relevant:
Test path and command:
Environment versions:
Observed result and reproducible evidence:
```

Do not choose a universal epsilon for latitude, metres, slope percent, angle, time or speed. Distinguish floating-point tolerance from DEM positional accuracy, measurement uncertainty and model error. Exact source hashes and segment identities require exact equality.

## Open risk register and sequencing

1. **NV-01 first:** establish independently checked WGS 84 distance and segment-identity references before interpreting terrain grade and pace.
2. **NV-02 next:** `DEMProvenance.vertical_datum` is metadata, not a performed vertical conversion. Verify datum compatibility before any datum-dependent combination; reject unsupported combinations or explicitly mark unknown reference.
3. **NV-03:** evaluate raw ascent/descent under noisy DEM data and treat adaptive interpolation as hypothetical positions, never original trail geometry.
4. **NV-04:** distinguish arithmetic validity from human-movement anomaly thresholds and predictive accuracy.
5. **NV-05:** cross-domain tests verify no implicit segment joining, source preservation, unavailable-data propagation and deterministic output values.
6. **NV-06:** evaluate regression and coverage evidence on the integrated commit.

P0 physical Garmin testing remains **on hold**. No source algorithms, CLI interface, schema files, or device readiness flags are changed by NV-00.
