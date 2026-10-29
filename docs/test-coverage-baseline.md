# Cross-domain test coverage baseline

The regression suite contains tests for F01–F10 and is executed in GitHub Actions on Python 3.11 and 3.12. This instrumentation adds **measured** statement and branch coverage to that existing suite; it does not change runtime behavior.

## Reproduce locally

```bash
python -m pip install -e '.[test]'
python -m pytest -q --cov=gpx_pipeline --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-report=json:coverage.json
```

The measured package is `gpx_pipeline` under `src/`. Tests and vendored XSD files are not included in executable source coverage. `term-missing` lists unexecuted statements. JSON and Cobertura XML files allow per-file inspection; branch coverage identifies missed branch alternatives, not proof of every semantic decision or safety property.

## CI evidence

The existing pull-request and `main` push workflow runs tests with the coverage instrumentation for both supported Python versions and uploads separate `coverage-python-3.11` and `coverage-python-3.12` artifacts (30-day retention). Use the run's **commit SHA**, not just its date, to associate a baseline with source code.

The instrumentation deliberately imposes **no** `--cov-fail-under` threshold while baseline percentages are unknown. Inspect the first completed run and rank uncovered lines and branches by functional risk: F01 XML safety, F02 geometry, F03 raster boundaries, F04 temporal constraints, F07/F08 schema and export integrity, F09 publication, F10 operational checks. Then add focused tests, remeasure, and only then decide whether a coverage floor is appropriate.

## Limits

- Percentage is a statement/branch execution statistic, **not** verified Garmin-device navigation, authenticated schema provenance, or formal correctness.
- Tests marked passed by CI and tests measured by pytest-cov are software-only. Device import and course conversion require independent physical field records.
- CI stores coverage data; it does not automatically interpret gaps or attest to quality.
- No external service, additional testing organization, gate or human sign-off is required.
