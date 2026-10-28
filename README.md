# GPX Processing Pipeline

An offline Python application for **GPX 1.1 validation, source-preserving geospatial analytics, terrain-aware DEM enrichment and device-specific Garmin navigation exports**. The primary deliverable is a reproducible enriched analytical dataset; Garmin navigation files are optional secondary outputs.

## Requirements and installation

Python **3.11+**. From a local checkout with the required dependencies available:

```bash
python -m pip install -e '.[test]'
gpx-pipeline --help
```

The installed command is `gpx-pipeline`. The program processes **local GPX files** and optional **local DEM rasters**; it does not download terrain data or sync Garmin devices.

## First commands

The following examples require actual GPX inputs. For commands producing files, the output **parent directory must already exist** and the selected destination must **not already exist**.

```bash
# Check full bundled GPX 1.1 schema plus spatial and temporal integrity.
gpx-pipeline validate route.gpx --format json

# Produce the canonical analytical dataset and route statistics.
mkdir -p results
gpx-pipeline analyze route.gpx --output results/analysis-01

# Optional terrain-derived products from an existing local DEM.
gpx-pipeline analyze route.gpx --output results/analysis-02 --dem terrain.tif --adaptive-sampling --forecast

# Explicitly generate two independent Garmin navigation exports.
gpx-pipeline export route.gpx --output results/garmin-01 --garmin etrex-se --garmin instinct-2x-tactical

# Compare two independently validated GPX sources.
gpx-pipeline compare --planned planned.gpx --recorded recorded.gpx --output results/comparison-01
```

Commands: `validate`, `analyze`, `process`, `export`, and `compare`. `process` produces analytics and only exports Garmin files when `--garmin` is explicitly specified. See [F09 quick start](docs/f09/quickstart.md) and [CLI reference](docs/f09/cli-reference.md) for options, output files, configuration and exit codes.

## Documentation

**[Documentation index — all ten domains F01–F10](docs/README.md)**

Start with [F09 orchestration and CLI](docs/F09-PIPELINE-ORCHESTRATION-CLI.md) for the application workflow, [F06 analytical processing](docs/F06-ANALYTICAL-PROCESSING.md) for source-preserving derived data, [F07 Garmin export](docs/F07-GARMIN-NAVIGATION-EXPORT.md) for device-specific files, and [F10 operational reliability](docs/F10-OPERATIONAL-RELIABILITY.md) for device-capacity and field-evidence limits.

The [F08 schema provenance](docs/f08-schema-provenance.md) records mirrored XSD source references and exact pinned bytes; it does **not** prove current live vendor binary identity.

## Verification

```bash
python -m pytest -q
```

The test suite contains domain regression/integration tests and the offline documentation-link check. This is a command to run in your environment, **not** a claim that CI or physical field tests were run for this README change.

**Navigation safety:** GPX/XSD validity and offline software readiness do not establish Garmin Explore/Connect import fidelity, off-course alerts or actual navigation on the eTrex SE or Instinct 2X Tactical. In particular, eTrex SE's conservative 200-point course gate differs from Explore website import ceilings; unknown Instinct 2X course capacity is not inferred. See [manual field-verification procedure](docs/f10-field-validation.md) before asserting device behavior.

## Scope

This is a personal, single-developer application. Source GPX geometry is not silently rerouted or simplified; DEM enrichment does not reconstruct missing trail geometry. The application does not generate FIT files or perform live Garmin synchronization.
