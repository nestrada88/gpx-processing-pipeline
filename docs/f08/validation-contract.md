# F08 — Production Schema Validation Contract

[← F08 overview](../F08-PRODUCTION-SCHEMA-VALIDATION.md) · [Bundled schema provenance](../f08-schema-provenance.md)

## Authoritative code and regression references

- [`src/gpx_pipeline/production_schemas.py`](../../src/gpx_pipeline/production_schemas.py)
- [`tests/test_f08_production_schemas.py`](../../tests/test_f08_production_schemas.py)
- [`src/gpx_pipeline/interoperability.py`](../../src/gpx_pipeline/interoperability.py)
- [Implementation PR #20](https://github.com/nestrada88/gpx-processing-pipeline/pull/20)

This document records **implemented behavior**, not a requirement that future code support network schema retrieval, extension export or physical Garmin device testing.

## Public result contract and call signatures

```python
validate_production_gpx(
    document: GPXDocument,
    *,
    limits: GPXLimits = GPXLimits(),
) -> ProductionSchemaResult

production_schema_registry()

verify_production_garmin_export(
    source: GPXDocument,
    exported,
    *,
    options=None,
)

parse_gpx_safe(payload: bytes) -> GPXDocument
```

`ProductionSchemaResult` is an immutable dataclass:

| Field | Type | Exact meaning |
| --- | --- | --- |
| `source_sha256` | `str` | SHA-256 hexadecimal digest of `document.xml`, the original GPX byte sequence. |
| `gpx11_valid` | `bool` | True for successful whole-document GPX 1.1 XSD validation. Invalid content raises rather than returning False. |
| `extension_roots_validated` | `int` | Number of recognized extension roots independently validated, not the number of nested child nodes or namespaces. |
| `namespaces` | `tuple[str, ...]` | Sorted distinct non-GPX namespaces encountered in the GPX tree. |

The validator returns no rewritten GPX content and does not insert a schemaLocation, Garmin extensions, or modified coordinates. A successful result establishes schema validity against the **bundled, pinned mirrored XSDs**. It does not prove the schema set is byte-identical to current vendor downloads.

## Package and integrity preconditions

Nine XSDs are loaded with `importlib.resources.files("gpx_pipeline").joinpath("schemas", name).read_bytes()`; there is no remote/fallback schema lookup. All files must be packaged as `schemas/*.xsd` under the `gpx_pipeline` package.

For each file, `_SCHEMA_FILES` binds one expected XML namespace, bundled filename and Git blob SHA-1. Verification computes:

```python
git_blob_sha1 = sha1(
    f"blob {len(data)}\\0".encode("ascii") + data
).hexdigest()
```

The displayed Python fragment is schematic: in actual code, `\\0` is a NUL byte escape in the f-string. The pin checks mirrored content integrity; SHA-1 blob pinning is not cryptographic vendor authentication. Replacing a bundled file without updating its expected pin causes `ProductionSchemaError("Schema integrity mismatch: ...")`.

Before compiling each `lxml.etree.XMLSchema`, F08 reuses F01's bounded XML parser to ensure an XSD `xs:schema` root, expected `targetNamespace`, and no direct `xs:import`, `xs:include`, `xs:redefine` or `xs:override` child. Those schema dependency mechanisms are unsupported. Missing schema files, bad namespace metadata, malformed XSD bytes and failed compilation are rejected.

The authoritative schema inventory and mirror/vendor links reside in [`docs/f08-schema-provenance.md`](../f08-schema-provenance.md). Avoid inventing guarantees from unverified live vendor byte identity.

## GPX and Garmin extension validation order

1. Compile and verify **all nine packaged schemas**. Schema compilation happens at validation invocation; no built-in persistent schema cache is claimed.
2. Parse the original `document.xml` with F01 secure `_read_xml(..., limits)`. This enforces applicable XML parsing/resource constraints.
3. Validate the complete XML tree against the bundled Topografix GPX 1.1 XSD. On GPX structural failure, raise `ProductionSchemaError` with the relevant validator error.
4. Iterate elements, ignoring non-element processing nodes and core GPX/empty namespaces.
5. Fail on any element whose non-GPX namespace is not registered in the bundled schema map. The GPX extension wildcard's lax validation is **not** a substitute for registered XSD checks.
6. For recognized extension namespace elements, identify the root of each namespace-connected subtree: if its parent's namespace is the same, its parent/root has already been schema-validated and the child is skipped as an independent root.
7. If a recognized extension is immediately under a GPX namespace parent, that parent must be `<extensions>`, not an arbitrary GPX element. The GPX 1.1 XSD checks whether such a container is structurally permitted in that location.
8. Independently validate each recognized extension root with its corresponding Garmin XSD. Invalid extension-root names or child content raise `ProductionSchemaError`; successful validations increment `extension_roots_validated`.
9. Return source SHA-256, `gpx11_valid=True`, validated extension-root count and sorted encountered namespace list.

**Important nuance:** The implementation regards a change in element namespace as an extension-root boundary. Its per-root validation does not imply that every possible multi-namespace nesting pattern or cross-namespace semantic relationship is supported. The full GPX schema and recognized extension root schemas are the actual validation evidence.

The Garmin Adventures target namespace is `http://www.garmin.com/xmlschemas/AdventuresExtensions/v1` (plural **Extensions**), unlike the filename's singular `AdventuresExtensionv1.xsd`.

## Error and security semantics

| Condition | Observable behavior |
| --- | --- |
| Missing bundled schema file | `ProductionSchemaError` |
| Git blob SHA-1 mismatch | `ProductionSchemaError` |
| XSD root/target namespace mismatch or disallowed schema dependency | `ProductionSchemaError` |
| Invalid compiled XSD | `ProductionSchemaError` |
| GPX 1.1 content/order/value violation | `ProductionSchemaError` |
| Unknown non-GPX extension namespace | `ProductionSchemaError` |
| Garmin extension root/schema violation | `ProductionSchemaError` |
| Resource-limit or malformed XML detected by F01 parsing | F01 parser/security exceptions may propagate |

The implemented checks prevent fallback to remote XSD resolution in this path. They do **not** certify arbitrary external file content, raster/DEM data, device behavior, or the trustworthiness of a caller-supplied GPX file beyond the parser and XSD checks.

## Working usage example: bundled GPX and Garmin XSDs

This self-contained GPX snippet uses a valid track with a Garmin TrackPointExtension v1 heart-rate element:

```python
from gpx_pipeline import parse_gpx
from gpx_pipeline.production_schemas import (
    validate_production_gpx,
    production_schema_registry,
)

source = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
     version="1.1" creator="f08-example">
  <trk><trkseg>
    <trkpt lat="12" lon="-86">
      <extensions>
        <gpxtpx:TrackPointExtension>
          <gpxtpx:hr>95</gpxtpx:hr>
        </gpxtpx:TrackPointExtension>
      </extensions>
    </trkpt>
    <trkpt lat="12.1" lon="-86.1"/>
  </trkseg></trk>
</gpx>"""

document = parse_gpx(source, strict=False)
result = validate_production_gpx(document)
assert result.gpx11_valid
assert result.extension_roots_validated == 1
assert result.namespaces == (
    "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
)
registry = production_schema_registry()
assert registry.gpx11_xsd is not None
print(result.source_sha256)
```

Use `strict=False` solely for the initial F01 parse. The subsequent `validate_production_gpx` call performs **production strict validation**. The `production_schema_registry()` return value is a compatibility adapter to F01/F07's older registry API and must not be mistaken for running this complete root-aware validator.

## Integration with F07 export

`verify_production_garmin_export(source, exported, *, options=None)` first validates the original `source` with F08, then parses and validates `exported.gpx` with F08, and finally invokes F07's `verify_garmin_export` using its local bundled GPX schema.

This helper passes an empty `extensions` map to the F07 compatibility registry after F08's stricter root-aware validations. Thus, for a source/export containing recognized populated Garmin extensions, F07's legacy extension checking can still report errors; **do not infer that the integration helper makes legacy F07 extension handling equivalent to F08 root validation**. In the current code, F07's exporter rejects populated `<extensions>` anyway. This integration is currently usable for conservative extension-free exported GPX.

The F07 software result can read `software_status="validated"` when checks find no blocking/unverified evidence; `physical_device_verified` remains `False`. Schema compliance is not Garmin application or hardware interoperability.

## Verification trace and limits

`tests/test_f08_production_schemas.py` contains regression cases for: successful compilation/registry inventory; valid source without extensions; invalid source element order, coordinates, elevations and timestamps; valid nested TrackPointExtension and PowerExtension; invalid heart-rate extension value and undeclared extension root; unknown namespace rejection; F01 XML resource limits; pinned bundled-file tampering; and F07 integration.

These committed tests and merged [PR #20](https://github.com/nestrada88/gpx-processing-pipeline/pull/20) provide implementation traceability, not a new test pass assertion. A configured checkout can run `python -m pytest -q`; actual CI and field evidence must be evaluated separately. No runtime code, schemas, pins, tests, dependencies or packaging are altered by this documentation.
