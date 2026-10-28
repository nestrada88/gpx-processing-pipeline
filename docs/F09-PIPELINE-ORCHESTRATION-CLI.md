# F09 — End-to-End Pipeline Orchestration and CLI

## Responsibility

F09 implements the offline single-run application: typed configuration, ordered source validation, command-selected F01–F08 analyses and device-targeted exports, a conventional command-line interface, and deterministic integrity-checked output publication. The installed executable is `gpx-pipeline` (declared under `[project.scripts]` in `pyproject.toml`). F09 implementation was merged in [PR #21](https://github.com/nestrada88/gpx-processing-pipeline/pull/21).

## Documentation index

- [Quick start](f09/quickstart.md): install, run, select outputs, interpret initial results.
- [Orchestration contract](f09/pipeline-orchestration.md): command-specific stage graph, source validation and output mapping.
- [Configuration contract](f09/configuration-contract.md): immutable `PipelineConfig` fields and invalid combinations.
- [CLI reference](f09/cli-reference.md): exact argument placement, subcommands, output and exit codes.
- [Output publication](f09/output-publication.md): no-overwrite staged publication, manifest, SHA-256, filesystem limits.

## Source-of-truth modules

| Responsibility | Source | Tests |
| --- | --- | --- |
| Command-specific orchestration | [`pipeline.py`](../src/gpx_pipeline/pipeline.py) | [`test_f09_pipeline.py`](../tests/test_f09_pipeline.py) |
| Configuration | [`pipeline_config.py`](../src/gpx_pipeline/pipeline_config.py) | Same |
| Installed CLI | [`cli.py`](../src/gpx_pipeline/cli.py) | Same |
| Safe artifact publication | [`output.py`](../src/gpx_pipeline/output.py) | Same |

## Command map

| Command | Mandatory processing | Optional outputs |
| --- | --- | --- |
| `validate` | Bounded GPX read, F08 production XSD, F02 geometry and F04 temporal gating | Stdout text or JSON only; no directory |
| `analyze` | Canonical F06 dataset and route statistics (with F05 catalog) | DEM enrichment, DEM-backed adaptive sampling, modeled activity forecast |
| `process` | Same analytical products as analyze | Same analytical options, plus explicitly selected Garmin exports |
| `export` | At least one explicit Garmin device target, GPX exports and offline verification | Additional explicitly selected device |
| `compare` | Independently validated planned and recorded inputs, F06 geodesic comparison | No DEM/forecast/device options for this command |

All commands first enforce the same ordered input checks; no selected output can bypass a mandatory validation failure. `process` **without** `--garmin` produces analytical outputs only. Device-specific GPX exports are never implicitly generated. F09 requests `verify_device_readiness` on exported navigation data, but passing software readiness does not establish real-device field testing.

## Shared invariants

1. F01 secure bounded parsing, F08 bundled strict XSD validation, F02 spatial validity and F04 error-level chronological validation precede derived operations.
2. F04 warnings are retained as warnings: only error-severity findings reject a GPX.
3. Source geometry is authoritative; DEM heights and interpolated samples are distinct derived products and cannot replace GPX observations.
4. F06 forecasted times are simulations. Missing grade does not silently become zero; `--assume-flat-grade` opts into the explicit assumption.
5. Garmin eTrex SE and Instinct 2X Tactical outputs are independent and explicitly requested. F08-backed F07 verification and F10 operational-readiness software checks do not prove Garmin import, device alerts or physical navigation.
6. A successful non-`validate` command creates a new immutable-looking output directory with `manifest.json`; an existing destination is rejected rather than overwritten.
7. Artifact hashes and input hashes are deterministic for identical bytes. No real-time timestamp is added to the publication manifest.

## Local execution requirements

Python >=3.11; install the package in a supported Python environment. The application works with local GPX files and optional local DEM rasters. The output directory's **parent must exist** and the selected output directory must **not** exist. GPX file input limit defaults to 8,000,000 bytes for each input; physical Garmin import/device behavior is out of scope.

## Verification and cross-domain boundaries

The committed [F09 integration tests](../tests/test_f09_pipeline.py) exercise validation, analytical outputs, timing assumptions, dual Garmin exports, planned/recorded comparison, invalid input, publication safety, repeatability, local DEM sampling and invalid options. Test presence and implementation PR merge are not a new test execution. Run `python -m pytest -q` in a configured checkout and inspect CI separately.

F01–F08 own domain-specific validation and algorithms. F09 orchestrates them, but does not redefine their scientific accuracy or introduce additional Garmin capabilities. F10 is responsible for operational reliability and field-evidence boundaries.
