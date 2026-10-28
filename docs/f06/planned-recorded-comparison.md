# F06 — Planned versus Recorded Comparison

[← F06 overview](../F06-ANALYTICAL-PROCESSING.md)

## Responsibility

Compare independently constructed planned and recorded analytical datasets using bounded geodesic matching against planned geometry.

Implementation: [`src/gpx_pipeline/planned_recorded.py`](../../src/gpx_pipeline/planned_recorded.py). Tests: [`tests/test_f06_planned_recorded.py`](../../tests/test_f06_planned_recorded.py). Implementation trace: [PR #14](https://github.com/nestrada88/gpx-processing-pipeline/pull/14).

## Public callable interfaces

- `compare_planned_recorded`
- `planned_recorded_json`

The functions and their record types are exported from the `gpx_pipeline` package. The source file is authoritative for exact Python type annotations; inputs must be constructed from the actual immutable canonical `AnalyticalDataset` where applicable.

## Implemented processing contract

- `compare_planned_recorded(planned, recorded, *, options=ComparisonOptions())` preserves separate planned/recorded SHA-256 lineage.
- Defaults: `tolerance_m=40.0`, `max_pairs=200_000`, `max_reference_edge_m=100_000.0`, `planned_duration_s=None`. Thresholds and computational limits are validated.
- Planned reference features include finite WGS 84 geodesic edges and isolated vertices; excessive reference edge length or point-feature pair counts fail closed. Recorded points are matched spatially, not by point index.
- `PointMatch` records nearest planned feature and deviation; point-sampled `OffRouteEvent` records excursions and rejoin within individual recorded segments. No independent segments are joined.
- `sample_coverage_fraction` is the fraction of **observed recorded samples** sufficiently near planned geometry, not a fraction of planned route traversed. `CheckpointProximity` is nearest recorded-vertex distance, not a verified visit.
- DEM elevation differences are only derived where explicit vertical datum labels agree and elevations are available; planned edge elevations may be linearly interpolated. Agreement of metadata text is not independently verified physical datum equivalence.
- Optional supplied `planned_duration_s` is not evidence of observed or forecast execution time. Results serialize deterministically.

## Reproducible API usage

The following is an **API usage fragment**: `dataset`, `planned_dataset`, `recorded_dataset`, and `gpx_bytes` (where referenced) must be supplied from a valid F01–F06 context; example local raster paths must point to suitable data.

```python
from gpx_pipeline import compare_planned_recorded, ComparisonOptions, planned_recorded_json
comparison = compare_planned_recorded(
    planned_dataset, recorded_dataset,
    options=ComparisonOptions(tolerance_m=40.0),
)
print(comparison.sample_coverage_fraction, comparison.max_deviation_m)
payload = planned_recorded_json(comparison)
```

## Failure, uncertainty and operational limits

Proximity cannot establish direction, progression, actual navigable trail coverage, route completion or checkpoint visitation; continuous trajectory matching and live off-route navigation are not provided.

Inspect exception types and validation in the linked source rather than interpreting a missing metric as zero. Incomplete coverage, optional stage omissions, explicit threshold choices and unverified vertical references must remain visible to downstream consumers. Derived products are not in-place edits to the source GPX.

## Verification trace

The repository includes `tests/test_f06_planned_recorded.py` for this responsibility. That file and implementation PR #14 provide traceable test/implementation artifacts; they do not independently demonstrate a fresh passing execution or full numerical certification. For a configured repository checkout, run `python -m pytest -q` and examine corresponding CI status. The present change is documentation-only.
