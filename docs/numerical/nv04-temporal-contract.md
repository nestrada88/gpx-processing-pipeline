# NV-04 — Temporal and kinematic numerical contract

Baseline: NV-03 merge `af2c56ae5b0e693b895f9fed21837a765e1671c2`.

## Numerical reference scope

- `tests/test_nv04_temporal_kinematic_contracts.py` contains fixed WGS 84 equatorial distances; independently derived speed and pace formulae; timezone-aware elapsed-time arithmetic; invalid/duplicate/reversed timestamps; and mathematically evaluated Tobler-model reference values.
- Forecast comparison independently computes flat-assumption moving time using `T = d * 3.6 / v_kmh` and verifies explicit 120 s rest and scenario ordering.
- Source GPX timestamps and bytes remain immutable. Missing DEM grades are unavailable by default. A zero-grade value is used only with explicit `missing_grade="assume"`.
- `SPEED_ANOMALY` is a nonfatal plausibility warning. Duplicate and reversed timestamps are numerical/chronological errors. Distinguish quality warnings from invalid arithmetic.

## Units and tolerances

| Quantity | Unit | Acceptance contract |
|---|---|---|
| Timestamp intervals | seconds | Exact equality for representable fixed time differences |
| Ellipsoidal distance | metres | 0.001 m absolute for fixed equatorial WGS 84 reference |
| Speed | metres/second | 0.00002 m/s absolute on fixed case |
| Pace | seconds/kilometre | 1e-8 relative on fixed case |
| Tobler speed | kilometres/hour | 1e-14 absolute/relative on model test cases |
| Forecast moving/elapsed time | seconds | 0.001 s absolute on fixed synthetic route |
| Source bytes / source fingerprint | bytes/hash | Exact equality |

These bounds describe floating-point comparison under synthetic reference inputs and do not quantify real-world human movement uncertainty or DEM height accuracy.

## Existing implementation and downstream risks

- `temporal.analyze_temporal` uses F02 segment-safe distances and timezone-normalized timestamps, with invalid chronology represented by findings and unknown speed/pace.
- `activity_forecasting.forecast_activity` uses Tobler speed on per-edge grades, with explicit incomplete forecast diagnostics.
- Nominal/optimistic/conservative scenarios use multipliers. They are hypothetical planning scenarios, **not statistically calibrated confidence intervals**.
- Checkpoint ETA excludes separately supplied route-wide rest because no rest allocation model is defined. Existing checkpoint tests cover this distinction.
- NV-05 must reconcile computed distances, source hashes and scenario outputs across the actual end-to-end pipeline; independent track segments must not imply travel or transfer time between them.

## Reproduction

```sh
python -m pytest -q tests/test_nv04_temporal_kinematic_contracts.py
python -m pytest -q
```

No production changes are included. Results must be established by CI or local execution on the exact commit; fixed reference tests are not claims of model prediction accuracy.

P0 Garmin physical device verification remains on hold.
