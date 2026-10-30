# S01-CHR v1.0.0 — Functional Implementation and Verification

**Governing baseline:** [S01-CHR-v1.0.0](S01-CHR-v1.0.0.md) (approved, merged in PR #73).  
**Exclusions:** S01-SCOPE-EXC-v1.0.0 remains unchanged.  
**Runtime scope:** Input characterization and diagnostics only; F08 schema validation and Garmin export behavior are not modified.

## User interface

```sh
gpx-pipeline characterize input.gpx
gpx-pipeline characterize input.gpx --declared-profile GPX-02
gpx-pipeline characterize input.gpx --max-input-bytes 25000000
```

This emits exactly one JSON report to standard output (no corrected GPX). Exit codes: 0 for accepted CHARACTERIZATION; 3 for XML, core XSD, or recognized-vendor admission failure; 4 for resource-limit or input-file failure. A declared profile is a user-supplied intent indicator; incompatible observed fields yield DECLARED_CONFLICT but do not override field-based results.

## Admission and parsing

- Separately verifies source-byte SHA-256, XML well-formedness, the repository's integrity-pinned GPX 1.1 XSD, and known Garmin extension XSDs.
- Unknown well-formed foreign extensions are retained in the original source and inventoried without assumed semantics; F08's stricter export rejection of such namespaces is preserved.
- Uses two incremental lxml `iterparse` passes. Completed track/route points are cleared with their preceding siblings; this avoids retaining an entire long point sequence in the parsed tree. Memory remains bounded by configured input and XML subtree budgets, with worst-case extension/metadata subtree size requiring separate empirical testing.
- Default GPXLimits admission guards are inherited from F01 (8,000,000 bytes, 300,000 nodes, depth 64); those are application limits, not GPX normative limits. Byte size can be overridden through the CLI. Node and depth limits are programmatic.
- Input path is rehashed after parsing to detect source changes between passes.
- Emits no downstream Layer 3/4 PASS or FAIL and does not mutate points, segments, elevations, timestamps, or XML source.

## Output

Report kinds CHARACTERIZATION and ADMISSION_FAILURE both conform to the approved `S01-CHR-REPORT.schema.json`. A failure report cannot advertise a successfully resolved profile. Coverage ratios, scopes and classification reasons follow S01-CHR section 2/3. The example in the approved contract remains illustrative, not runtime evidence.

Known analytical limits: vertical datum and actual privacy intent remain UNKNOWN/NOT_CERTIFIED unless independent evidence is supplied. Longitude crossing is flagged without publishing a misleading naive bounding box; precise split multi-segment geographic-envelope algorithms remain a separate validation area. The resource report records STREAMING but does not invent a measured peak RSS value or payload size.

## Verification

`tests/test_s01_characterization.py` provides 24 named CHRV scenario functions, parameterizing CHRV-013 over Garmin TPX v1 and v2, plus a negative source-preservation test. Each executable case validates its result against the approved JSON Schema and checks independent data expectations. The standalone CLI command should be smoke-tested through the installed console entrypoint. Existing F01/F08/F09 tests retain their established stricter validation contracts.

**Evidence policy:** Local smoke-test results from a simplified schema stub are development feedback only. Only successful CI on the commit and any separately executed full-schema tests are valid repo-backed operational evidence. Neither establishes empirical GNSS field validation or device readiness.
