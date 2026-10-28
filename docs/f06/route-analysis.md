# F06 — Route Analysis

[← F06 overview](../F06-ANALYTICAL-PROCESSING.md)

## Responsibility

Derive route and segment summaries exclusively from a canonical AnalyticalDataset, without new GPX parsing or competing distance/elevation calculations.

Implementation: [`src/gpx_pipeline/route_analysis.py`](../../src/gpx_pipeline/route_analysis.py). Tests: [`tests/test_f06_route_analysis.py`](../../tests/test_f06_route_analysis.py). Implementation trace: [PR #13](https://github.com/nestrada88/gpx-processing-pipeline/pull/13).

## Public callable interfaces

- `analyze_route`
- `route_analysis_json`

The functions and their record types are exported from the `gpx_pipeline` package. The source file is authoritative for exact Python type annotations; inputs must be constructed from the actual immutable canonical `AnalyticalDataset` where applicable.

## Implemented processing contract

- `analyze_route(dataset, *, options=RouteAnalysisOptions())` enforces the analytical dataset schema and point/segment identity contracts. `flat_grade_percent` defaults to `1.0` and must be finite and nonnegative.
- `RouteSegmentSummary` and `RouteStatistics` aggregate independent track/route geometry without creating inter-segment edges. Cumulative source distances must be monotonic and begin at zero for a segment.
- `GradeDistribution` categorizes signed grades into uphill, downhill and flat bands; valid grades are weighted by geodesic **edge distance**, not counts of vertices. Undefined grades have a distinct count.
- Elevation extrema and raw ascent/descent are derived from existing DEM-aligned point data; incomplete terrain cannot be presented as complete ascent/descent. Incomplete recorded timing remains explicitly unavailable.
- `CheckpointAssociation` references F05 waypoint catalog information; its `near_route_vertex` and `nearest_vertex_m` mean proximity to a recorded **vertex**, not continuous-polyline projection or checkpoint visitation.
- Results carry `source_sha256`, DEM source/datum, data-quality diagnostics and deterministic UTF-8 JSON output.

## Reproducible API usage

The following is an **API usage fragment**: `dataset`, `planned_dataset`, `recorded_dataset`, and `gpx_bytes` (where referenced) must be supplied from a valid F01–F06 context; example local raster paths must point to suitable data.

```python
from gpx_pipeline import analyze_route, RouteAnalysisOptions, route_analysis_json
report = analyze_route(dataset, options=RouteAnalysisOptions(flat_grade_percent=1.0))
print(report.statistics.total_distance_m, report.diagnostics)
serialized = route_analysis_json(report)
```

## Failure, uncertainty and operational limits

No moving-time claim where the canonical dataset lacks F04 moving-time totals. No smoothing of ascent/descent, trail reconstruction, forecast, or implied continuous-route coverage.

Inspect exception types and validation in the linked source rather than interpreting a missing metric as zero. Incomplete coverage, optional stage omissions, explicit threshold choices and unverified vertical references must remain visible to downstream consumers. Derived products are not in-place edits to the source GPX.

## Verification trace

The repository includes `tests/test_f06_route_analysis.py` for this responsibility. That file and implementation PR #13 provide traceable test/implementation artifacts; they do not independently demonstrate a fresh passing execution or full numerical certification. For a configured repository checkout, run `python -m pytest -q` and examine corresponding CI status. The present change is documentation-only.
