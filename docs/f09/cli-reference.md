# F09 — Installed CLI Reference

[← F09 overview](../F09-PIPELINE-ORCHESTRATION-CLI.md) · [Quick start](quickstart.md)

Implementation: [`src/gpx_pipeline/cli.py`](../../src/gpx_pipeline/cli.py); packaging: [`pyproject.toml`](../../pyproject.toml); tests: [`tests/test_f09_pipeline.py`](../../tests/test_f09_pipeline.py).

## Invocation

The entry point `gpx-pipeline` is installed by the package. `argparse` requires one subcommand from `validate`, `analyze`, `process`, `export`, or `compare`. The global `--debug` belongs **before** the subcommand. `--help` is available at the root and subcommand levels.

```text
gpx-pipeline [--debug] validate INPUT [--format {text,json}] [--max-input-bytes N]
gpx-pipeline [--debug] analyze INPUT --output DIR [--dem RASTER] [--adaptive-sampling] [--forecast] [--assume-flat-grade] [--max-input-bytes N]
gpx-pipeline [--debug] process INPUT --output DIR [--dem RASTER] [--adaptive-sampling] [--forecast] [--assume-flat-grade] [--garmin DEVICE]... [--max-input-bytes N]
gpx-pipeline [--debug] export INPUT --output DIR --garmin DEVICE [--garmin DEVICE]... [--max-input-bytes N]
gpx-pipeline [--debug] compare --planned FILE --recorded FILE --output DIR [--max-input-bytes N]
```

`DEVICE` must be one of `etrex-se` or `instinct-2x-tactical`, without duplicates. `process` can omit `--garmin`, producing analysis only. `export` must select at least one target. `--dem` provides a **local** raster; `--adaptive-sampling` requires it. `--forecast` enables F06 simulated timing; `--assume-flat-grade` explicitly supplies a missing-grade assumption and is only valid together with forecast.

`--max-input-bytes N` applies independently to each input GPX (default 8,000,000 bytes), not to the full output directory or DEM raster size. Rasters have their own domain resource constraints.

## Standard output, errors and help

On successful `validate`:
- `--format text` (default): `Valid GPX 1.1; spatial and temporal checks passed`.
- `--format json`: a one-line JSON object with `valid: true` and `sha256` of the source input bytes.

On successful other commands, stdout prints the chosen output directory path. Diagnostics go to **stderr** as `CODE: description`; unexpected processing exceptions use `PROCESSING_FAILED` unless global `--debug` re-raises them for a traceback.

## Exit status and error output

| Exit code | Meaning |
| ---: | --- |
| 0 | Successful command |
| 1 | Other processing failure, including `NO_OUTPUT`, unexpected errors and unmapped `PipelineError` categories |
| 2 | Invalid CLI arguments (argparse) or `CONFIG_INVALID` |
| 3 | `GPX_INVALID`, `SPATIAL_INVALID`, `TEMPORAL_INVALID` |
| 4 | `INPUT_UNAVAILABLE`, `INPUT_LIMIT` |
| 5 | `GARMIN_INCOMPATIBLE` |
| 6 | `OUTPUT_FAILED` |

`--debug` changes exception handling for execution errors: Python exceptions can propagate instead of being converted to a numeric return. It does not redefine domain validation or physical Garmin capability.

## Examples

```bash
gpx-pipeline validate route.gpx --format json
gpx-pipeline analyze route.gpx --output results/analytics
gpx-pipeline analyze route.gpx --output results/forecast --forecast --assume-flat-grade
gpx-pipeline process route.gpx --output results/full --garmin etrex-se --garmin instinct-2x-tactical
gpx-pipeline export route.gpx --output results/nav --garmin instinct-2x-tactical
gpx-pipeline compare --planned planned.gpx --recorded recorded.gpx --output results/diff
gpx-pipeline --debug validate route.gpx
```

Each output destination must be unused, with an existing parent directory. The CLI does not create directories named in these examples except the destination itself after successful staging. See [configuration](configuration-contract.md), [orchestration](pipeline-orchestration.md) and [publication](output-publication.md).

## Guidance boundary

This CLI follows the project's command-line design conventions through an `argparse` interface. This document describes concrete implemented commands rather than claiming complete conformance with every recommendation at https://clig.dev/. The CLI has no built-in web APIs, streaming sensor upload, Garmin device synchronization, FIT generation or automatic routing.
