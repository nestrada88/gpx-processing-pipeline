# F06 — DEM Raster Sampling Integration

[← F06 overview](../F06-ANALYTICAL-PROCESSING.md)

## Responsibility

Connect a configured local rasterio DEM to F06 adaptive analytical sampling without introducing a second raster interpolation implementation.

Implementation: [`src/gpx_pipeline/dem_sampling_adapter.py`](../../src/gpx_pipeline/dem_sampling_adapter.py). Tests: [`tests/test_dem_sampling_adapter.py`](../../tests/test_dem_sampling_adapter.py). Implementation trace: [PR #17](https://github.com/nestrada88/gpx-processing-pipeline/pull/17).

## Public callable interfaces

- `sample_terrain_from_dem`
- `dem_sampling_json`

The functions and their record types are exported from the `gpx_pipeline` package. The source file is authoritative for exact Python type annotations; inputs must be constructed from the actual immutable canonical `AnalyticalDataset` where applicable.

## Implemented processing contract

- `sample_terrain_from_dem(dataset, raster_path, *, dem_options=DEMOptions(), sampling_options=SamplingOptions(), vertical_datum=None, uncertainty_m=None)` opens a local single-band DEM and returns `DEMSamplingResult`.
- F03 sampling semantics are reused: WGS 84-to-raster CRS transformation, nearest/bilinear pixel-center interpretation, mask/NoData and out-of-coverage handling, explicit meter elevation units, unsupported band scaling/offset rejection.
- `DEMOptions` governs raster file size and interpolation configuration. The adapter separately bounds **all raster callback operations**, including adaptive midpoint probes, rather than counting emitted points alone. `sample_operations` reports executed callback operations.
- The adapter retains raster access only during this call and returns a frozen `DEMSamplingResult(schema_version, sampling, provenance, sample_operations)`. `provenance` includes DEM source, CRS, resolution, method, declared vertical datum and optional uncertainty.
- `vertical_datum` is caller-declared metadata, **not a conversion**. Unknown uncertainty remains unknown; raster resolution does not establish vertical accuracy. Missing samples remain missing.
- The analytical source fingerprint and original GPX geometry remain unchanged. `dem_sampling_json` emits deterministic UTF-8 JSON.

## Reproducible API usage

The following is an **API usage fragment**: `dataset`, `planned_dataset`, `recorded_dataset`, and `gpx_bytes` (where referenced) must be supplied from a valid F01–F06 context; example local raster paths must point to suitable data.

```python
from gpx_pipeline import sample_terrain_from_dem, DEMOptions, SamplingOptions, dem_sampling_json
result = sample_terrain_from_dem(
    dataset, "terrain.tif",
    dem_options=DEMOptions(method="bilinear"),
    sampling_options=SamplingOptions(max_output_points=50000),
)
print(result.sample_operations, result.provenance)
payload = dem_sampling_json(result)
```

## Failure, uncertainty and operational limits

Requires a prepared local DEM with suitable CRS/metadata; no source acquisition, vertical-datum conversion, multi-tile mosaic, hidden trail reconstruction or live Garmin navigation is implemented.

Inspect exception types and validation in the linked source rather than interpreting a missing metric as zero. Incomplete coverage, optional stage omissions, explicit threshold choices and unverified vertical references must remain visible to downstream consumers. Derived products are not in-place edits to the source GPX.

## Verification trace

The repository includes `tests/test_dem_sampling_adapter.py` for this responsibility. That file and implementation PR #17 provide traceable test/implementation artifacts; they do not independently demonstrate a fresh passing execution or full numerical certification. For a configured repository checkout, run `python -m pytest -q` and examine corresponding CI status. The present change is documentation-only.
