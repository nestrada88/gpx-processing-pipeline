# F06 — Terrain-Adaptive Analytical Sampling

[← F06 overview](../F06-ANALYTICAL-PROCESSING.md)

## Responsibility

Produce an immutable derived sampling representation along geodesic interpolations between existing original vertices, preserving canonical geometry.

Implementation: [`src/gpx_pipeline/terrain_sampling.py`](../../src/gpx_pipeline/terrain_sampling.py). Tests: [`tests/test_terrain_sampling.py`](../../tests/test_terrain_sampling.py). Implementation trace: [PR #16](https://github.com/nestrada88/gpx-processing-pipeline/pull/16).

## Public callable interfaces

- `terrain_adaptive_sample`
- `terrain_sampling_json`

The functions and their record types are exported from the `gpx_pipeline` package. The source file is authoritative for exact Python type annotations; inputs must be constructed from the actual immutable canonical `AnalyticalDataset` where applicable.

## Implemented processing contract

- `terrain_adaptive_sample(dataset, sample_elevation_m, *, dem_source_description, options=SamplingOptions())` takes a caller-supplied callback `(latitude, longitude) -> elevation in meters | None`.
- `SamplingOptions` defaults: `max_spacing_m=200.0`, `elevation_residual_m=2.0`, `min_spacing_m=5.0`, `max_depth=12`, `max_output_points=50_000`; input validation and caps constrain interpolation work/output.
- Sampling refines original geodesic edges for spacing and DEM midpoint-versus-endpoint elevation residual. A derived point has `original_edge_end_index` and `edge_fraction`; an original vertex retains `source_point_index`. This identity must remain explicit in downstream analysis.
- `SampledSegment` keeps track/route segments separate. `SampledPoint` records source/derived status, coordinates, cumulative distance, DEM elevation/grade availability and lineage. `SamplingResult` reports source fingerprint, DEM description, options, segments and diagnostics.
- Missing DEM coverage is not interpreted as zero height, zero slope or proof of a flat trail. Sampling depth/spacing limits and diagnostic resolution limits are not a guarantee of sufficient real-world geometry.
- Caller is responsible for consistent DEM and vertical datum semantics; callback behavior is not a built-in raster access service. `terrain_sampling_json` is deterministic JSON.

## Reproducible API usage

The following is an **API usage fragment**: `dataset`, `planned_dataset`, `recorded_dataset`, and `gpx_bytes` (where referenced) must be supplied from a valid F01–F06 context; example local raster paths must point to suitable data.

```python
from gpx_pipeline import terrain_adaptive_sample, SamplingOptions, terrain_sampling_json
result = terrain_adaptive_sample(
    dataset, lambda lat, lon: None,
    dem_source_description="no elevation coverage",
    options=SamplingOptions(max_spacing_m=200.0),
)
print(result.diagnostics)
payload = terrain_sampling_json(result)
```

## Failure, uncertainty and operational limits

Geodesic interpolation does not reconstruct unseen switchbacks, identify a surveyed path, mutate original GPX, guarantee DEM coverage, or infer terrain movement feasibility.

Inspect exception types and validation in the linked source rather than interpreting a missing metric as zero. Incomplete coverage, optional stage omissions, explicit threshold choices and unverified vertical references must remain visible to downstream consumers. Derived products are not in-place edits to the source GPX.

## Verification trace

The repository includes `tests/test_terrain_sampling.py` for this responsibility. That file and implementation PR #16 provide traceable test/implementation artifacts; they do not independently demonstrate a fresh passing execution or full numerical certification. For a configured repository checkout, run `python -m pytest -q` and examine corresponding CI status. The present change is documentation-only.
