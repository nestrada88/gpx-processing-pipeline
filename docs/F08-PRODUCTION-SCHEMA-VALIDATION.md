# F08 — Production GPX and Garmin Schema Validation

## Scope and implementation

F08 provides strict, offline XML Schema validation of GPX 1.1 documents and recognized Garmin extension **root** elements, using bundled and integrity-pinned XSD bytes. It does not modify source GPX and does not validate physical Garmin navigation behavior.

- Implementation: [`src/gpx_pipeline/production_schemas.py`](../src/gpx_pipeline/production_schemas.py)
- Detailed contract: [`f08/validation-contract.md`](f08/validation-contract.md)
- Existing schema origin and mirror references: [`f08-schema-provenance.md`](f08-schema-provenance.md)
- Regression evidence: [`tests/test_f08_production_schemas.py`](../tests/test_f08_production_schemas.py)
- Implementation traceability: [PR #20](https://github.com/nestrada88/gpx-processing-pipeline/pull/20)

**Core distinction:** Schema content was taken from traceable public GitHub mirrors and is pinned by exact Git-blob SHA-1. Those pins establish reproducible **mirrored bytes**, not byte identity with live Topografix/Garmin vendor downloads, independent publisher authenticity, or device compatibility.

## Bundled schema inventory

XSD files live in `src/gpx_pipeline/schemas/` and are packaged through `[tool.setuptools.package-data] gpx_pipeline = ["schemas/*.xsd"]` in `pyproject.toml`.

| Bundled file | Declared target namespace |
| --- | --- |
| `gpx.xsd` | `http://www.topografix.com/GPX/1/1` |
| `GpxExtensionsv3.xsd` | `http://www.garmin.com/xmlschemas/GpxExtensions/v3` |
| `TrackPointExtensionv1.xsd` | `http://www.garmin.com/xmlschemas/TrackPointExtension/v1` |
| `TrackPointExtensionv2.xsd` | `http://www.garmin.com/xmlschemas/TrackPointExtension/v2` |
| `WaypointExtensionv1.xsd` | `http://www.garmin.com/xmlschemas/WaypointExtension/v1` |
| `TripExtensionsv1.xsd` | `http://www.garmin.com/xmlschemas/TripExtensions/v1` |
| `PressureExtensionv1.xsd` | `http://www.garmin.com/xmlschemas/PressureExtension/v1` |
| `PowerExtensionv1.xsd` | `http://www.garmin.com/xmlschemas/PowerExtension/v1` |
| `AdventuresExtensionv1.xsd` | `http://www.garmin.com/xmlschemas/AdventuresExtensions/v1` |

The Adventures namespace intentionally uses plural `AdventuresExtensions`. GPX 1.1 provides the core structure; the eight Garmin XSDs are validated independently for recognized extension roots.

## Processing flow and integrity boundaries

```text
Source GPXDocument (F01)
            |
    Load nine packaged XSDs
            |
  Check pinned Git-blob SHA-1
            |
 Validate target namespaces and
 reject XSD imports/includes/etc.
            |
   Compile local XMLSchema objects
            |
 F01 bounded secure XML reparse
            |
 GPX 1.1 whole-document XSD check
            |
 Reject unknown namespaces and
 validate Garmin extension roots
            |
 ProductionSchemaResult
```

F08 uses `_read_xml(..., GPXLimits)` for XML input and schema parsing, disallows external XSD dependencies, and makes **no runtime schema downloads**. Strict checking rejects nonconforming GPX core structure, invalid extension values and unknown namespaces. Its output records the SHA-256 of original source bytes, GPX validity, number of validated Garmin extension roots and sorted recognized namespaces.

## Public interfaces

| API | Responsibility |
| --- | --- |
| `validate_production_gpx(document, *, limits=GPXLimits())` | Strict GPX document plus registered Garmin extension-root validation; returns `ProductionSchemaResult`. |
| `production_schema_registry()` | Supplies bundled local paths in F01's legacy `SchemaRegistry` format for existing consumers. |
| `verify_production_garmin_export(source, exported, *, options=None)` | Validates source and generated GPX with F08, then invokes F07 offline compatibility verification. |
| `parse_gpx_safe(payload)` | Reuses F01 bounded non-strict parsing before production validation; not a replacement for full validation. |

`ProductionSchemaError` represents invalid or missing bundled XSDs, failed pin checks, XSD compilation/namespace violations and nonconforming GPX or Garmin extension content. F01 XML parsing and resource exceptions can also surface.

## Cross-domain contract

- **F01:** Canonical GPX object, parser security, XML resource limits, and the legacy schema-registry interface. F01's earlier descendant-by-descendant extension handling is not equivalent to F08 root-aware validation of Garmin complex types.
- **F07:** Geometry-preserving navigation exports and offline software compatibility findings. F08 can supply actual bundled schema evidence, but **F07 exporter currently rejects populated extension elements**; F08 independently validates source documents with recognized extensions.
- **F09:** Pipeline orchestration and user-facing CLI behavior; invoking F08 is not the same as guaranteeing a specific CLI switch or command without inspecting F09.
- **F10:** Field evidence and physical-device behavior. Passing an XSD cannot prove Garmin Explore/Connect conversion, alerts, off-course behavior, transfer success or device capacity.

## Verification and residual limitations

The F08 regression module exercises bundled schema compilation, registry inventory, valid/invalid GPX structure, valid nested Garmin trackpoint extension, invalid child values, valid power extension, unknown namespaces, undeclared extension root elements, resource limits, package-integrity tampering and F07 integration. These tests use the **bundled schema definitions**; the tests' existence and PR merge do not prove a fresh passing test execution.

Additional limitations: no live vendor-byte comparison; no external schema dependency graph; no runtime network fetching; no Garmin extension generation by F07; no physical-device verification. An XSD cannot establish real-world route quality, DEM accuracy or device workflow compatibility.

For callable examples, schema error semantics, and root-validation rules, see [validation-contract.md](f08/validation-contract.md). For provenance records, continue using the existing [schema provenance document](f08-schema-provenance.md).
