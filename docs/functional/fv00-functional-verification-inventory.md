# FV-00 — Functional Verification Inventory and Execution Matrix

## 1. Scope and evidence

- Repository: `nestrada88/gpx-processing-pipeline`
- Verified reference baseline: NV-20 merge `4dde0d1a16da23330d131a048d2317c0195df5ab` (PR #65).
- This inventory identifies functional behavior to verify through the **installed CLI and generated artifacts**, rather than claiming coverage of these behaviors merely because individual Python functions have regression tests.
- Requirements sources: repository `README.md`, `docs/F09-PIPELINE-ORCHESTRATION-CLI.md`, `docs/F07-GARMIN-NAVIGATION-EXPORT.md`, `docs/F10-OPERATIONAL-RELIABILITY.md`, and their linked domain contracts.
- Execution platform: Linux CI with Python 3.11/3.12. Native Windows tests and physical Garmin checks are **not** implied.
- NV-20 baseline: 497 passing tests per Python environment; 97% combined coverage; 45 missed statements and 43 partial branches. Numerical CI is not functional-acceptance evidence.

## 2. Primary functional sequence

**Functional priority:** enriched analytical dataset first; Garmin device-specific files second. The CLI is the external application boundary.

| ID | Responsibility | CLI invocation / test scenario | Observable contract | Artifact / evidence |
|---|---|---|---|---|
| FV-01 | Installed CLI and configuration | `gpx-pipeline --help`; invalid flags/command combinations | Discoverable subcommands; deterministic nonzero exit and diagnostic for invalid combinations | CLI stdout/stderr and exit code |
| FV-02 | F01/F02/F04/F08 input gates | `validate source.gpx --format json`; invalid namespace, XSD, spatial, temporal data | No downstream output on invalid mandatory input; valid source emits machine-readable confirmation | stdout JSON and rejection evidence |
| FV-03 | Canonical analytical dataset | `analyze source.gpx --output DIR` on multitrack/multisegment and routes | Retain original coordinate order, segment identity and recorded data; derived values remain separate | Analytical JSON, source hash, route report |
| FV-04 | DEM enrichment | `analyze ... --dem raster.tif` with known, missing and incompatible terrain | DEM provenance and datum explicit; missing height remains null; no silent altitude substitution | Dataset + terrain/elevation report and reproducible DEM fixture |
| FV-05 | Adaptive geodesic sampling | `analyze ... --dem raster.tif --adaptive-sampling` | Bounded, DEM-aware intermediates explicitly labeled as derived geodesic estimates, never source vertices/actual trail bends | Sampling report, original-vs-derived point identity |
| FV-06 | Timing and forecast separation | `analyze ... --forecast` with/without `--assume-flat-grade` | Recorded timestamps preserved; forecast remains unavailable when grade missing unless explicit assumptions; scenario ETA and rest are modeled | Forecast JSON + original source hash |
| FV-07 | Waypoint catalog | GPX containing checkpoints and descriptive waypoints | Preserve names/coordinates, distinguish explicit classifications and inferred proximity, no fabricated Garmin turn cues | Canonical waypoint catalog |
| FV-08 | Planned-versus-recorded | `compare --planned P --recorded R --output DIR` | Independently validate P and R; geodesic off-route/rejoin events; absent recorded times not invented; incompatible DEM datum stays incomparable | Comparison JSON + event diagnostics |
| FV-09 | Garmin dual export | `export source.gpx --output DIR --garmin etrex-se --garmin instinct-2x-tactical` | Independently labeled GPX files/verification JSON; exact source track/route geometry, waypoint XML/checkpoint lineage retained; no unrequested device outputs | Both device GPXs, manifests and verification reports |
| FV-10 | Device software gates | eTrex course over conservative 200-point limit, optional Explore website line restrictions; Instinct unknown limits | Reject known incompatibilities without modifying geometry; unknown capacities are explicitly unverified, not invented | Device readiness and compatibility findings |
| FV-11 | Single-run orchestration | `process` with and without `--garmin`; `analyze` and `validate` | No implicit Garmin export; command-specific output sets; ordered validation before processing | Output tree and manifest contents |
| FV-12 | Deterministic publication | Repeat same input to different new destinations; retry occupied destination | Byte-identical deterministic artifacts, valid SHA-256 manifests; existing destination never overwritten and incomplete staging removed | Manifest verification + negative collision evidence |
| FV-13 | Offline operation and bounded inputs | Run without network access; oversized GPX, malformed XML, nonexistent raster, unsafe destination | Never download schema/DEM/device data; enforce size/resource constraints and failure classification | Exit status, no output, unchanged source |
| FV-14 | CLI error contract | Invalid GPX, invalid spatial/temporal data, missing input, Garmin incompatibility, publication failure | Distinct documented error category and stable exit code, no success-looking partial output | Captured stdout/stderr, status, filesystem state |
| FV-15 | Source lineage / end-to-end repeatability | Compare SHA-256 source bytes before and after each command; rerun across Python versions | Source remains unchanged; output lineage covers source and DEM when present; deterministic JSON | Source digest and per-artifact digest audit |

## 3. Suggested source fixtures

| Fixture | Purpose | Minimum grounded conditions |
|---|---|---|
| GPX-A | Baseline valid route | WGS84 fixed vertices, known segment boundary, source timestamps |
| GPX-B | Multitrack/multisegment | At least two track segments with separated endpoints, one route and named waypoints; never bridge a gap |
| GPX-C | Time/grade incompleteness | Missing DEM heights and timestamps; verify null propagation and explicit assumptions |
| GPX-D | Comparison departure/rejoin | Planned line and recorded offset fixes, with varied timing, geodesic reference offsets |
| GPX-E | eTrex limit | One track exceeding 200 points; independently verify source preservation and expected software rejection |
| DEM-A | Controlled surface | Local metric raster with declared horizontal CRS, explicit elevation units and vertical datum label |
| DEM-B | Missing/invalid surface | NoData cells, missing CRS, unsupported units or invalid affine; rejection versus unavailable distinction |
| GPX-X | Invalid-input corpus | Broken XML, invalid XSD, out-of-range geodesic coordinates, invalid chronology and unregistered extensions |

All fixtures should be synthetic or independently permitted to distribute, with explicit expected values, SHA-256 digests and no location-specific claims about real trail fidelity.

## 4. Execution and acceptance criteria

1. Use an isolated, newly created output parent and a **previously nonexistent** target for each successful publication. Preserve the source and captured command results.
2. Exercise the installed `gpx-pipeline` entrypoint in a subprocess; Python function-level tests alone are insufficient evidence for CLI acceptance.
3. Check generated files **by decoding their contents**, not merely checking filenames. Recompute SHA-256 for every manifested artifact.
4. Compare source coordinate tokens and ordered track/route segment structure from input versus Garmin export. The only intentional GPX tree change is the root creator attribute.
5. Include positive and negative cases for each mandatory validation gate. A rejected operation must not leave a published output directory.
6. Separate verified software transfer readiness from unverified Garmin Explore/Connect conversion and actual hardware navigation.
7. Preserve reported uncertainty: DEM is a sampled elevation surface, adaptive interpolation is not trail reconstruction, forecasts are modeled rather than recorded times.

## 5. Functional test branches (sequential)

| Branch | Responsibility | Technical deliverable |
|---|---|---|
| `test/fv01-cli-command-contracts` | CLI command syntax, parsing, error categories, installation smoke | Executable subprocess tests and captured outputs |
| `test/fv02-analytical-deliverables` | Enriched dataset, DEM, adaptive sampling, timing, waypoints and provenance | Integration fixtures with exact artifact assertions |
| `test/fv03-comparison-and-export` | Planned/recorded comparison, device-labeled Garmin outputs and known software limits | Command-level output and geometry audits |
| `test/fv04-publication-and-offline` | Determinism, source immutability, offline operation, resource/error boundaries | End-to-end failure and repeatability tests |
| `docs/fv05-functional-evidence-report` | Consolidate verified functionality and unresolved requirements | Test matrix with pass/fail/untested evidence and artifact links |

Branch names represent the **next intended technical sequence**, not already created Git branches. Work is sequential, single-developer, without review or approval gates.

## 6. Coverage boundary and open work

- **Not tested in FV-00:** any new CLI execution, fixture run, Garmin Explore/Connect import, hardware navigation or actual Windows-native publication.
- **P0 field verification remains on hold:** independent offline navigation on eTrex SE and Instinct 2X Tactical, device course limits as encountered, alert/vibration behavior, course conversion and actual import geometry.
- **Scientific external validity remains open:** real-world route shape, elevation vertical-datum conversion, ground-truth DEM error and actual pace/ETA forecasting error.
- Distinguish `unverified` from `failed`; do not label a software-only pass as physical device success.

## 7. Current disposition

FV-00 provides the **functional acceptance inventory and execution order**. Its completion is documentary; it does not assert that the fifteen functional contracts have been run end-to-end. Begin with FV-01 using CLI subprocess behavior and repeatable, synthetic source fixtures.
