# F09 — Pipeline Orchestration Contract

[← F09 overview](../F09-PIPELINE-ORCHESTRATION-CLI.md)

Implementation: [`src/gpx_pipeline/pipeline.py`](../../src/gpx_pipeline/pipeline.py) and [`tests/test_f09_pipeline.py`](../../tests/test_f09_pipeline.py).

## Public types and entry point

```python
run_pipeline(config: PipelineConfig) -> PipelineResult
```

`PipelineError(ValueError)` retains a stable `code: str` and human-readable message. `PipelineResult` is an immutable dataclass with `command: str`, `output_dir: Path | None`, `artifacts: tuple[str, ...]` and `input_sha256: tuple[tuple[str, str], ...]`. `artifacts` contains sorted **relative artifact paths**, not the bytes themselves. Source fingerprints refer to `GPXDocument.xml` bytes, which come from the input GPX. `validate` returns no artifact directory or files.

The source implementation is sequential and single-run; no background jobs, live data downloads, Garmin synchronization or global mutable processing state are introduced.

## Mandatory validation order (each GPX input)

1. Verify the local GPX path exists and is a file and that its byte size does not exceed `config.max_input_bytes`.
2. Read source bytes and call F01 `parse_gpx(..., strict=False, limits=GPXLimits(max_bytes=limit))`.
3. Require F08 `validate_production_gpx(..., limits=GPXLimits(max_bytes=limit))` using bundled pinned XSDs. The earlier non-strict parse does not bypass this strict production validation.
4. Check F02 `validate_spatial(document).valid`. Invalid geometry becomes `PipelineError("SPATIAL_INVALID", ...)`.
5. Call F04 `analyze_temporal(document)`. Reject findings with `severity=="error"` only, using `PipelineError("TEMPORAL_INVALID", ...)`; warnings alone do not reject the file.
6. Only after successful validation execute the requested operations. General parsing/schema/value failures within the input-validation block are wrapped as `PipelineError("GPX_INVALID", ...)`.

Input file absence and read/access errors become `INPUT_UNAVAILABLE`; oversized GPX becomes `INPUT_LIMIT`. Both planned and recorded inputs to `compare` go through the same sequence independently.

## Command-specific stage graph

| Command | Implementation stages |
| --- | --- |
| `validate` | Return input SHA-256, no publication. |
| `compare` | Independently read planned and recorded; F05 catalogs + canonical F06 datasets; F06 geodesic comparison; publish comparison JSON. No DEM parameter to this mode. |
| `analyze` | F05 `enrich_waypoints`; optional F03 `enrich_dem`; canonical F06 `build_analytical_dataset`; F06 route analysis; optional DEM-backed adaptive sampling and forecast; publish. |
| `process` | All `analyze` outputs, plus zero or more explicitly selected Garmin target exports/verification. |
| `export` | At least one explicit Garmin target; for each target, F07 export, F08-backed F07 compatibility verification and F10 software device-readiness verification; publish. |

For each selected Garmin device, F09 chooses `explore-web-tracks` for `etrex-se` and `connect-course` for `instinct-2x-tactical`. It passes `require_xsd=True` to the compatibility path. `software_status=="incompatible"` or `software_compatible=False` from operational verification fails with `GARMIN_INCOMPATIBLE`. A software status of `validated` is **not** a proof of Garmin transfer or field navigation.

F06 activity forecasting uses `ForecastOptions(missing_grade="assume")` only when `assume_flat_grade=True`; otherwise missing grade is `"unavailable"`. Adaptive sampling with `sample_terrain_from_dem` requires a configured `dem_path` and produces a separate derived artifact, not GPX geometry edits.

## Artifact map

| Operation | Relative path |
| --- | --- |
| Canonical analytical dataset | `analytical/dataset.json` |
| Route analysis | `analytical/route-analysis.json` |
| Adaptive sampling when requested | `analytical/terrain-sampling.json` |
| Forecast when requested | `analytical/activity-forecast.json` |
| Planned vs recorded | `comparison/planned-vs-recorded.json` |
| Device GPX | `navigation/<device>.gpx` |
| Device GPX manifest | `navigation/<device>-manifest.json` |
| F07 compatibility verification | `verification/<device>.json` |
| F10 operational-readiness report | `verification/<device>-operational.json` |
| Publication manifest (added by output layer) | `manifest.json` |

## Failure/publishing boundary

`run_pipeline` gathers in-memory artifact bytes before publication. If a mandatory stage fails, it does not create a successfully published output directory. If no output operations were selected, it raises `PipelineError("NO_OUTPUT", ...)`. Publication `OSError` and `OutputError` become `PipelineError("OUTPUT_FAILED", ...)`.

The `output.py` staging/rename mechanism offers an atomic directory rename **where supported on the same filesystem**; this is not a universal guarantee against system-level failure after rename or external filesystem interference.

The test module covers process/analyze/validate/export/compare, repeated output manifest identity, invalid source, output collision, DEM workflow and device target restrictions. No new tests were executed when authoring this documentation.
