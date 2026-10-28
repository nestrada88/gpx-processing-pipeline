# F09 — Quick Start

[← F09 overview](../F09-PIPELINE-ORCHESTRATION-CLI.md) · [CLI reference](cli-reference.md) · [Output publication](output-publication.md)

## Install and inspect help

Requires Python 3.11+ in a configured environment with dependencies available. From the repository checkout:

```bash
python -m pip install -e .
gpx-pipeline --help
gpx-pipeline process --help
```

The installed command comes from `pyproject.toml`: `gpx-pipeline = "gpx_pipeline.cli:main"`. This tool uses local data and does not download DEM rasters or synchronize Garmin devices.

## Validate before generating outputs

```bash
gpx-pipeline validate route.gpx --format json
```

A valid document prints compact JSON containing `valid: true` and the source SHA-256. Text is the default `--format`. `validate` does **not** accept `--output` and creates no output directory. It checks the bundled F08 GPX schema, F02 geometry and F04 temporal error findings, not actual Garmin readiness.

## Generate analytics

Create a new output directory under an existing parent:

```bash
mkdir -p results
gpx-pipeline analyze route.gpx --output results/run-01
```

Generated files include `analytical/dataset.json`, `analytical/route-analysis.json` and `manifest.json`. Do not pre-create `results/run-01`; existing destinations cannot be overwritten.

With a suitable existing local DEM:

```bash
gpx-pipeline analyze route.gpx --output results/run-02 --dem terrain.tif --adaptive-sampling --forecast
```

The DEM must exist and satisfy F03/F06 raster assumptions. `--adaptive-sampling` requires `--dem` and produces analytical geodesic interpolations, **not** reconstructed trail bends. Missing grade makes simulated moving time unavailable unless explicitly assumed:

```bash
gpx-pipeline analyze route.gpx --output results/run-03 --forecast --assume-flat-grade
```

This assumption is not a measurement of flat terrain.

## Device-specific exports

```bash
gpx-pipeline export route.gpx --output results/device-run --garmin etrex-se --garmin instinct-2x-tactical
```

This produces independent `navigation/<device>.gpx`, `navigation/<device>-manifest.json`, `verification/<device>.json` and `verification/<device>-operational.json` for each chosen target, plus the directory `manifest.json`. A source must contain navigable track/route geometry. F07/F08 verification and F10 readiness are **offline software evidence**, not confirmation of Explore/Connect import or real-device course fidelity.

`process` always adds analytical data; it only adds Garmin files when `--garmin` is provided:

```bash
gpx-pipeline process route.gpx --output results/combined --garmin etrex-se
```

## Planned versus recorded comparison

```bash
gpx-pipeline compare --planned planned.gpx --recorded recorded.gpx --output results/comparison
```

Both GPX files are independently validated. The comparison output is `comparison/planned-vs-recorded.json`. Its geodesic proximity measurements do not prove that the planned route was fully traversed or that checkpoints were visited.

## Inspect an output

`manifest.json` lists the command, SHA-256 input fingerprints and the SHA-256 and byte count of each generated artifact. Values are deterministic for identical inputs and configuration, subject to external raster input bytes. Compare digests before using a result as reproducible evidence.

The CLI prints the published output path on successful non-validation commands. Runtime errors print coded diagnostics to stderr. See [exit codes](cli-reference.md#exit-status-and-error-output) and [publication guarantees](output-publication.md).

## Run tests

```bash
python -m pip install -e '.[test]'
python -m pytest -q tests/test_f09_pipeline.py
```

These commands are instructions to run locally, not a claim that tests were executed as part of documentation authoring.
