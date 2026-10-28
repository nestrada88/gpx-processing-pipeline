# F06 — Activity Forecasting

[← F06 overview](../F06-ANALYTICAL-PROCESSING.md)

## Responsibility

Create explicitly simulated terrain-aware pedestrian time estimates, without modifying GPX observations or presenting predictions as recorded measurements.

Implementation: [`src/gpx_pipeline/activity_forecasting.py`](../../src/gpx_pipeline/activity_forecasting.py). Tests: [`tests/test_f06_activity_forecasting.py`](../../tests/test_f06_activity_forecasting.py). Implementation trace: [PR #15](https://github.com/nestrada88/gpx-processing-pipeline/pull/15).

## Public callable interfaces

- `forecast_activity`
- `tobler_speed_kmh`
- `activity_forecast_json`

The functions and their record types are exported from the `gpx_pipeline` package. The source file is authoritative for exact Python type annotations; inputs must be constructed from the actual immutable canonical `AnalyticalDataset` where applicable.

## Implemented processing contract

- `forecast_activity(dataset, *, options=ForecastOptions())` first checks route-analysis consistency. `tobler_speed_kmh(grade_percent, *, min_speed_kmh=0.3, max_speed_kmh=8.0)` applies a bounded Tobler walking-speed model to signed percent grade; this is a heuristic rather than a calibrated prediction.
- `ForecastOptions` defaults include `missing_grade="unavailable"`, `assumed_grade_percent=0.0`, speed bounds `0.3..8.0` km/h, `rest_seconds=0.0`, `optimistic_factor=0.8`, `conservative_factor=1.3`, `start_time=None`.
- Missing grade makes affected travel times unavailable by default; explicit `missing_grade="assume"` enables flagged assumed grade. Model speed is not a measurement of the user's field pace.
- `ForecastEdge`, `ForecastSegment` and `ForecastScenario` separate forecastable coverage, simulated moving durations, rest allowances and optional finish times. Optimistic/nominal/conservative factors are hypothetical scenarios, not probability bounds or confidence intervals.
- Finish timestamps require a timezone-aware start time, and output is rendered in UTC. Segments remain independent; no unobserved connecting geometry or transfer time is invented.
- `CheckpointETA` requires an exact, unambiguous original vertex match and available preceding timing. Route-wide rest is **not allocated** among checkpoint ETAs, and this limitation is diagnosed.
- `activity_forecast_json` serializes deterministic JSON and explicitly converts configured `start_time` to ISO format.

## Reproducible API usage

The following is an **API usage fragment**: `dataset`, `planned_dataset`, `recorded_dataset`, and `gpx_bytes` (where referenced) must be supplied from a valid F01–F06 context; example local raster paths must point to suitable data.

```python
from gpx_pipeline import forecast_activity, ForecastOptions, activity_forecast_json
forecast = forecast_activity(
    dataset, options=ForecastOptions(missing_grade="unavailable"),
)
print(forecast.scenarios, forecast.diagnostics)
payload = activity_forecast_json(forecast)
```

## Failure, uncertainty and operational limits

No weather/fatigue model, calibrated uncertainty, real-world pace guarantee, route projection, live device ETA, rest distribution to checkpoints or Garmin export.

Inspect exception types and validation in the linked source rather than interpreting a missing metric as zero. Incomplete coverage, optional stage omissions, explicit threshold choices and unverified vertical references must remain visible to downstream consumers. Derived products are not in-place edits to the source GPX.

## Verification trace

The repository includes `tests/test_f06_activity_forecasting.py` for this responsibility. That file and implementation PR #15 provide traceable test/implementation artifacts; they do not independently demonstrate a fresh passing execution or full numerical certification. For a configured repository checkout, run `python -m pytest -q` and examine corresponding CI status. The present change is documentation-only.
