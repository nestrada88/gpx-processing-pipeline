# NV-03 — Terrain numerical verification contract

Baseline: `main` at `4d021c04f9056b5e784ac7fb6fddaf39db9cf996` (NV-02 merge).

## Numerical reference tests

- `tests/test_nv03_terrain_numerical_contracts.py`: fixed synthetic heights, raw ascent/descent, vertical translation invariance, missing elevation boundaries, independent analytic Horn slope and relief on a 100 m projected raster, masked-cell behavior, and explicit demonstration of raw ascent sensitivity to alternating height jitter.
- `tests/test_nv03_adaptive_sampling_contracts.py`: geodesic interpolation spacing when budgets permit, unchanged GPX bytes, original-vertex lineage, and resolution-limit diagnostics when maximum recursion depth prevents the requested spacing.
- Existing `test_f03_terrain.py`, `test_terrain_sampling.py`, `test_f03_f06_numerical_terrain_hardening.py`, `test_f03_f06_terrain_analytical_consistency.py` remain regression inputs.

## Computation semantics and cautions

The published `TerrainSegment.ascent_m` and `descent_m` are **raw sums of consecutive observed DEM height differences** where both ends are available. These values are sampling- and noise-sensitive; this phase neither silently filters them nor treats raw totals as uncertainty-calibrated field truth. A constant vertical height offset leaves raw differences and grade invariant; that property does not make heights in incompatible vertical datums interchangeable.

The surface slope uses Horn 3×3 derivatives on an orthogonal, horizontally metric raster. On a linear plane with 10 m change per 100 m eastward cell and 20 m per 100 m southward cell, the expected slope is `degrees(atan(hypot(0.1, 0.2)))`. Relief is maximum minus minimum over a complete specified neighborhood.

Adaptive points are *hypothetical points along an original WGS 84 geodesic*, not recovered trail geometry. `SAMPLING_RESOLUTION_LIMIT` reports insufficient refinement capacity. Point-count budget exhaustion raises a controlled `SamplingError`; neither condition authorizes silently simplifying source GPX.

## Determinism and tolerances

- Raw ascent/descent and synthetic integer height statistics: exact numeric equality.
- Analytical Horn plane slope and relief: 1e-10 absolute in degrees/metres, respectively.
- Adaptive edge spacing: 0.001 m absolute slack over 200 m target for floating-point accumulation.
- Total interpolated route length: 0.01 m absolute tolerance over the synthetic equatorial segment.
- GPX serialized source bytes and original vertex indices: exact equality.

These are numerical test tolerances, not DEM absolute accuracy estimates.

## Scope and evidence

No production algorithms or public output contracts are changed. The tests characterize existing raw metrics and adaptive processing behavior. Filtered ascent/descent or modified sampling policies require separate explicit semantics and independent benchmarks if later justified. All test outcomes remain unverified until CI or local execution is observed.

Run:

```sh
python -m pytest -q tests/test_nv03_terrain_numerical_contracts.py tests/test_nv03_adaptive_sampling_contracts.py
python -m pytest -q
```

P0 physical Garmin field testing remains on hold. NV-04 covers temporal and forecast arithmetic; NV-05 covers cross-domain agreement.
