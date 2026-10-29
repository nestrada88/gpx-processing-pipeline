# NV-05 — Cross-domain numerical consistency contract

Base: NV-04 merge commit `1c5e7f91d5d8cbb274de03d52e61d55291948c36`.

## Executable verification

`tests/test_nv05_cross_domain_consistency.py` exercises the actual F09 orchestrator using two deliberately disconnected track segments. The input carries explicit timestamps; the test raster has constant metre-valued elevation and known geographic coverage.

### Complete synthetic DEM

The `analyze` and `process` commands, with identical analytical options and **without Garmin targets**, must produce byte-identical common analytical products:

- `analytical/dataset.json`
- `analytical/route-analysis.json`
- `analytical/terrain-sampling.json`
- `analytical/activity-forecast.json`

The test independently verifies segment boundaries and one fixed WGS 84 equatorial distance, the route total equals the sum of independent segments, flat DEM yields zero ascent/descent, recorded segment time totals are 60 + 120 = 180 seconds (not 3,720 seconds across the track gap), and derived forecast times exist without replacing any recorded timestamps.

The source fingerprint must agree across all analytical reports, and every published payload must match its manifest byte length and SHA-256. The original GPX input must remain unchanged.

### Missing DEM

With no DEM, derived elevations and grade must remain unavailable. Raw ascent/descent are not published as zero, and the forecast must stay incomplete unless grade is explicitly assumed. Observed elapsed time remains available independently of DEM coverage.

## Numerical contract

- Exact equality for common output bytes, source and artifact hashes, segment identities, total recorded seconds, complete flat heights and missingness.
- Absolute 0.001 m for fixed geodesic reference; 1e-6 m for reconciliation of reported aggregate with constituent segment distances.
- The synthetic DEM is a mathematical fixture, not evidence of real-world terrain accuracy.
- No implicit time, distance or terrain joins may bridge disconnected source segments.

## Execution

```sh
python -m pytest -q tests/test_nv05_cross_domain_consistency.py
python -m pytest -q --cov=gpx_pipeline --cov-branch --cov-report=term-missing
```

This branch adds tests and documentation only. The physical Garmin validation workstream remains on hold. NV-06 must evaluate CI results, regressions and coverage before the consolidated numerical verification work is considered complete.
