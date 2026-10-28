# GPX Processing Pipeline — Documentation

This is the navigation entry point for the **offline, single-developer GPX processing application**. It produces an enriched, source-preserving analytical dataset first and, when selected, device-labeled Garmin GPX navigation files. The 10 domain documentation sets correspond to merged implementation domains; documentation and software validation do **not** imply successful physical-device import or navigation.

## Start here

1. [Repository README](../README.md): installation requirements, initial commands, overview and verification.
2. [F09 quick start](f09/quickstart.md): first GPX validation and published analytical outputs.
3. [F09 CLI reference](f09/cli-reference.md): flags, command constraints, diagnostics and exit codes.
4. [F09 output publication](f09/output-publication.md): deterministic manifest, no-overwrite destination, integrity checks.
5. [F10 manual field procedure](f10-field-validation.md): physically observed Garmin import/navigation evidence, **not executed by automated tests**.

## Domain index

| Domain | Responsibility | Entry document |
| --- | --- | --- |
| F01 | GPX 1.1 interoperability, parsing and security limits | [GPX Interoperability](domains/F01-gpx-interoperability.md) |
| F02 | Spatial geometry and geodesic integrity | [Spatial Integrity](F02-SPATIAL-INTEGRITY.md) |
| F03 | DEM enrichment and terrain analytics | [DEM Enrichment](F03-DEM-ENRICHMENT.md) and [Terrain Analytics](F03-TERRAIN-ANALYTICS.md) |
| F04 | Time sequence and kinematic plausibility | [Temporal and Kinematic Integrity](F04-TEMPORAL-KINEMATIC-INTEGRITY.md) |
| F05 | Source waypoint interpretation and checkpoint catalog | [Waypoint Intelligence](F05-WAYPOINT-INTELLIGENCE.md) |
| F06 | Analytical data, distance, sampling, comparison and forecasting | [Analytical Processing](F06-ANALYTICAL-PROCESSING.md) |
| F07 | Geometry-preserving Garmin navigation exports and compatibility checks | [Garmin Navigation Export](F07-GARMIN-NAVIGATION-EXPORT.md) |
| F08 | Strict bundled GPX/Garmin XML Schema validation | [Production Schema Validation](F08-PRODUCTION-SCHEMA-VALIDATION.md) |
| F09 | End-to-end orchestration, CLI and artifact publication | [Pipeline Orchestration and CLI](F09-PIPELINE-ORCHESTRATION-CLI.md) |
| F10 | Device-course readiness, fault tests and manual field evidence contracts | [Operational Reliability](F10-OPERATIONAL-RELIABILITY.md) |

### Focused reference sets

- [F06 analytical dataset](f06/analytical-dataset.md), [route analysis](f06/route-analysis.md), [adaptive sampling](f06/terrain-adaptive-sampling.md), [DEM sampling](f06/dem-sampling-integration.md), [forecasting](f06/activity-forecasting.md), and [planned/recorded comparison](f06/planned-recorded-comparison.md).
- [F07 export contract](f07/navigation-export.md) and [compatibility verification](f07/compatibility-verification.md).
- [F08 validation contract](f08/validation-contract.md) and [bundled schema provenance](f08-schema-provenance.md).
- [F09 orchestration](f09/pipeline-orchestration.md), [configuration](f09/configuration-contract.md), [CLI reference](f09/cli-reference.md), and [publication](f09/output-publication.md).
- [F10 device readiness](f10/device-readiness.md), [field evidence contract](f10/field-evidence-contract.md), [reliability verification](f10/reliability-verification.md), and [manual field procedure](f10-field-validation.md).

## Verification and traceability

- Run `python -m pytest -q` to execute the installed regression suite, including the Markdown link-integrity test.
- The link check verifies local relative file paths and recognized Markdown heading anchors. External links and live Garmin/vendor pages are **not** revalidated by this offline check.
- The XSD package contains traceably pinned *mirrored schema bytes*. [F08 provenance](f08-schema-provenance.md) does not claim current official-vendor binary identity.
- F07/F10 software compatibility findings are not physical Garmin certifications. Actual device/course evidence must be collected separately and tied to original/exported file hashes.

## Technical boundaries

The source GPX geometry remains authoritative. DEM interpolation is derived analytical context, not recovered trail topology. Garmin Explore website import limits, eTrex course-point limits, and unknown Instinct 2X course capacity are separate constraints. No automatic rerouting, FIT generation, live Garmin transfer, remote DEM retrieval or physical field testing is supplied by the documentation itself.

This index intentionally preserves the existing F01 and F08/F10 document locations to avoid unnecessary historical path changes.
