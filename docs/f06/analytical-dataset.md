# F06 — Canonical Analytical Dataset

[← F06 overview](../F06-ANALYTICAL-PROCESSING.md)

## Responsibility

Build an immutable analytical master from F01–F05 without replacing recorded GPX geometry, recorded elevation text or timestamp text.

Implementation: [`src/gpx_pipeline/analytical.py`](../../src/gpx_pipeline/analytical.py). Tests: [`tests/test_f06_analytical.py`](../../tests/test_f06_analytical.py). Implementation trace: [PR #12](https://github.com/nestrada88/gpx-processing-pipeline/pull/12).

## Public callable interfaces

- `build_analytical_dataset`
- `analytical_json`

The functions and their record types are exported from the `gpx_pipeline` package. The source file is authoritative for exact Python type annotations; inputs must be constructed from the actual immutable canonical `AnalyticalDataset` where applicable.

## Implemented processing contract

- `build_analytical_dataset(document, *, dem=None, waypoints=None, include_temporal=True)` requires F02-valid geometry. DEM and waypoint data are optional; `include_temporal` controls F04 analysis.
- Source points are keyed by `(kind, index, segment, point)`. Tracks and routes are segmented separately; waypoints are retained without invented route edges.
- A DEM's height is an analytical field distinct from the source's recorded `ele` text; observed times remain source text and kinematic estimates occupy derived fields.
- The dataset carries `source_sha256`, DEM source and declared vertical datum, optional waypoint catalog, segment coverage/completeness flags and diagnostic strings. Missing enrichment remains absent rather than becoming zero.
- Invalid F02 geometry, inconsistent DEM/terrain identities, segment mismatch and incompatible waypoint identity are rejected rather than silently reconciled.
- `analytical_json` emits UTF-8, sorted-key, compact JSON with a trailing newline and rejects nonfinite JSON values. A hash of source GPX content is lineage, not proof of external raster accuracy.

## Reproducible API usage

The following is an **API usage fragment**: `dataset`, `planned_dataset`, `recorded_dataset`, and `gpx_bytes` (where referenced) must be supplied from a valid F01–F06 context; example local raster paths must point to suitable data.

```python
from gpx_pipeline import parse_gpx, build_analytical_dataset, analytical_json
document = parse_gpx(gpx_bytes, strict=False)
dataset = build_analytical_dataset(document, include_temporal=False)
payload = analytical_json(dataset)
print(dataset.source_sha256, len(dataset.segments), len(payload))
```

## Failure, uncertainty and operational limits

Does not reconstruct a trail, synthesize temporal observations, infer hazard semantics, or itself perform planned/recorded comparison or activity simulation.

Inspect exception types and validation in the linked source rather than interpreting a missing metric as zero. Incomplete coverage, optional stage omissions, explicit threshold choices and unverified vertical references must remain visible to downstream consumers. Derived products are not in-place edits to the source GPX.

## Verification trace

The repository includes `tests/test_f06_analytical.py` for this responsibility. That file and implementation PR #12 provide traceable test/implementation artifacts; they do not independently demonstrate a fresh passing execution or full numerical certification. For a configured repository checkout, run `python -m pytest -q` and examine corresponding CI status. The present change is documentation-only.
