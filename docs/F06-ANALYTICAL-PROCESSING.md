# F06 — Analytical Processing

## Role and system boundaries

F06 composes validated F01–F05 information into a canonical, source-preserving analytical representation, then offers distinct route reporting, planned/recorded matching, modeled activity timing, terrain-adaptive sampling and raster-backed sampling integration. This is an **analytical application**, not a navigation-device exporter or an alternative GPX parser. The source GPX retains authoritative coordinates, original elevation and timestamp observations, ordering, and track/route segment boundaries.

## Domain documents

- [Canonical Analytical Dataset](f06/analytical-dataset.md) — `analytical.py`, [PR #12](https://github.com/nestrada88/gpx-processing-pipeline/pull/12)
- [Route Analysis](f06/route-analysis.md) — `route_analysis.py`, [PR #13](https://github.com/nestrada88/gpx-processing-pipeline/pull/13)
- [Planned versus Recorded Comparison](f06/planned-recorded-comparison.md) — `planned_recorded.py`, [PR #14](https://github.com/nestrada88/gpx-processing-pipeline/pull/14)
- [Activity Forecasting](f06/activity-forecasting.md) — `activity_forecasting.py`, [PR #15](https://github.com/nestrada88/gpx-processing-pipeline/pull/15)
- [Terrain-Adaptive Analytical Sampling](f06/terrain-adaptive-sampling.md) — `terrain_sampling.py`, [PR #16](https://github.com/nestrada88/gpx-processing-pipeline/pull/16)
- [DEM Raster Sampling Integration](f06/dem-sampling-integration.md) — `dem_sampling_adapter.py`, [PR #17](https://github.com/nestrada88/gpx-processing-pipeline/pull/17)

The canonical dataset is upstream of the other F06 operations. Route analysis is reused by comparison and forecasting; terrain-adaptive sampling is independent of comparison/forecasting. The DEM adapter supplies F03 raster data to the adaptive sampler; the six modules do **not** comprise a mandatory linear execution sequence.

## Invariants

1. Preserve original source GPX and distinguish recorded, DEM-derived, analytically interpolated and forecast values.
2. Join analytical point identities by source `(kind, index, segment, point)`; do not connect distinct source segments or silently infer missing vertices.
3. Treat absent DEM elevation, grade, recorded time and coverage as absent; incomplete aggregation must not be described as a complete route result.
4. Distinguish F05 nearest-**vertex** checkpoint information from F06 planned route geodesic **edge** matching; neither proves checkpoint visitation.
5. Preserve independent planned/recorded SHA-256 source identifiers. A cryptographic source fingerprint does not certify the scientific quality of source measurements.
6. Keep optional DEM datum descriptive, unless a valid transformation is explicitly implemented elsewhere. Do not conflate geographic raster pixel size with meter accuracy.
7. Serialize finite, deterministic analytical JSON; failure diagnostics and resource restrictions are part of result interpretation.
8. Do not treat simulated activity ETAs as recorded observations or calibrated probabilities.
9. Any interpolated coordinate along the WGS 84 geodesic of an original edge is derived geometry, not recovered trail geometry.

## Dependency map

```text
F01 GPX + F02 spatial integrity
    + optional F03 DEM/terrain, F04 timing and F05 waypoints
                       |
                 AnalyticalDataset
             /         |         \
   Route Analysis   Adaptive    DEM sampling adapter
     /      \       sampling    -> adaptive sampling
Comparison  Forecasting
```

This is a conceptual dependency sketch, not a requirement that downstream computations execute in this exact order.

## API and reproducibility

All primary public functions and record types are re-exported through `gpx_pipeline.__init__`. Each linked document describes signatures, configuration, output contracts, failure handling, example Python calls and source-specific limitations. Only use an enrichment feature when its required upstream evidence exists. New output is analytics, not an in-place GPX rewrite.

## Verification basis and limitations

The paired test modules are `tests/test_f06_analytical.py`, `tests/test_f06_route_analysis.py`, `tests/test_f06_planned_recorded.py`, `tests/test_f06_activity_forecasting.py`, `tests/test_terrain_sampling.py`, and `tests/test_dem_sampling_adapter.py`. Implementation PRs #12–#17 are merged. Test presence and merges alone are not proof of current runtime pass status; inspect CI and run `python -m pytest -q` in a configured checkout. This documentation-only change does not execute tests or certify Garmin field performance.

## Domain boundaries

F07 is responsible for Garmin navigation products; F08 is responsible for production schema validation; F09 is responsible for orchestration/CLI; F10 is responsible for operational reliability and field evidence. F06 must not claim those responsibilities simply because its outputs may be consumed downstream.
