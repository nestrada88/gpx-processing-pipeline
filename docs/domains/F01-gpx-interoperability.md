# F01 — GPX Interoperability

## Purpose and boundary

F01 provides secure Topografix GPX 1.1 XML ingestion, optional local XSD
validation, immutable source-byte retention, and lossless byte serialization.
It is the input foundation for F02–F10, **not** a geometry repair engine,
temporal plausibility verifier, DEM sampler, or Garmin navigation exporter.

**Implementation:** `src/gpx_pipeline/interoperability.py`.
**Public exports:** `src/gpx_pipeline/__init__.py`.
**Tests:** `tests/test_f01_interoperability.py` and
`tests/integration/test_f01_f03_end_to_end.py`.

## Input and output contracts

- Input to `parse_gpx`: **bytes** containing XML whose root is exactly
  `{http://www.topografix.com/GPX/1/1}gpx`.
- Output: `GPXDocument(xml: bytes)`, a frozen dataclass retaining a byte
  snapshot of the input XML. The stored XML is not normalized or regenerated.
- `GPXDocument.tree()` returns a **newly parsed, detached** `lxml` element
  root. Mutating this tree does not mutate the document snapshot.
- `serialize_gpx(document)` returns the preserved XML bytes without
  reformatting coordinates, namespace prefixes, metadata, or extensions.
- Successful non-strict parsing **does not** establish XSD structural validity,
  WGS 84 coordinate ranges, chronological consistency, or device compatibility.
- Direct construction of `GPXDocument(xml=...)` does **not** invoke the
  `parse_gpx` validation entry point. Applications handling untrusted input
  must parse/validate first.

## Public Python interface

| Symbol | Contract |
| --- | --- |
| `GPX11_NAMESPACE` | `http://www.topografix.com/GPX/1/1` |
| `parse_gpx(source: bytes, *, registry: SchemaRegistry \| None = None, limits: GPXLimits = GPXLimits(), strict: bool = True) -> GPXDocument` | Bounded XML parse, root namespace check, and optional strict XSD validation |
| `serialize_gpx(document: GPXDocument) -> bytes` | Returns original XML byte snapshot |
| `GPXDocument.tree() -> lxml.etree._Element` | Independently parsed element root |
| `SchemaRegistry(gpx11_xsd=None, extensions={})` | Local paths for main GPX XSD and explicitly registered extension namespace XSDs |
| `GPXLimits(max_bytes=8_000_000, max_nodes=300_000, max_depth=64)` | Per-parse security/resource ceilings; values must be positive |
| `GPXError` | General invalid input or unsupported operation |
| `GPXSecurityError` | DTD, entity or resource-limit rejection; subtype of `GPXError` |
| `GPXSchemaError` | Root, GPX XSD or extension XSD validation failure; subtype of `GPXError` |

`SchemaRegistry.extensions` maps **namespace URI strings** to local XSD file
paths. Registry paths are not downloaded at runtime.

## Parse and validation sequence

1. Enforce the input byte ceiling.
2. Parse with `lxml`, external entity resolution disabled, DTD loading
   disabled, network access disabled, and large-tree parsing disabled.
3. Reject XML containing a document type declaration, unresolved entities,
   or a tree exceeding the node/depth limits.
4. Require the exact GPX 1.1 root element and namespace.
5. If `strict=True` (the default), require a local `gpx11_xsd`, validate
   the complete document against it, then validate elements belonging to each
   explicitly registered extension namespace against its local schema.
6. Return the original input bytes as a `GPXDocument`.

**Important extension limitation:** F01's `_validate` validates **each
element** whose namespace is registered as an independent XSD root. This
can reject nested extension elements that are valid only within a containing
extension structure. It also does not automatically reject every unregistered
third-party namespace; GPX XSD lax extension handling can admit such content.
The production-oriented F08 validation layer supplies its own extension-root
policy. Do not describe F01 alone as comprehensive Garmin extension validation.

## Verified examples

Non-strict secure ingestion, with no XSD structural guarantee:

```python
from gpx_pipeline import parse_gpx, serialize_gpx

source = (
    b'<gpx xmlns="http://www.topografix.com/GPX/1/1" '
    b'version="1.1" creator="example"/>'
)
document = parse_gpx(source, strict=False)
assert serialize_gpx(document) == source
```

Explicit local strict XSD validation:

```python
from pathlib import Path
from gpx_pipeline import SchemaRegistry, parse_gpx

document = parse_gpx(
    source,
    registry=SchemaRegistry(gpx11_xsd=Path("/absolute/path/to/gpx.xsd")),
)
```

The second example requires `source` from the first example and an actual
local GPX 1.1 XSD at the configured path. Omission of the schema in strict
mode raises `GPXSchemaError`. For the bundled production schema registry,
refer to `src/gpx_pipeline/production_schemas.py` and
[`docs/f08-schema-provenance.md`](../f08-schema-provenance.md).

## Errors and security limits

| Condition | Result |
| --- | --- |
| Malformed XML | `GPXError` |
| Wrong root/local namespace | `GPXSchemaError` |
| DTD or unresolved entity | `GPXSecurityError` |
| Input bytes, tree nodes or depth over limit | `GPXSecurityError` |
| Strict mode without GPX XSD | `GPXSchemaError` |
| GPX or registered extension schema mismatch | `GPXSchemaError` |
| Invalid nonpositive `GPXLimits` | `ValueError` |

`GPXDocument.tree()` reparses with a byte limit sufficient for the
snapshot and the **default node/depth limits**. It does not retain custom
limits passed to the original `parse_gpx` call. The stored snapshot may
therefore be accepted by `parse_gpx` with custom limits but rejected when
accessed through `tree()` if the default node/depth ceilings are exceeded.

## Invariants and exclusions

- Original coordinate text, extension XML, element order and track-segment
  boundaries are preserved **in the stored bytes**.
- Detached-tree mutation does not rewrite the source snapshot.
- F01 performs **no** spatial coordinate repair, distance computation,
  temporal validation, terrain interpolation, forecasting, GPX route
  optimization, or Garmin-specific export adaptation.
- Strict validation requires a configured schema. Non-strict parsing is a
  secure XML/root check, **not** a GPX schema validation substitute.
- GPX validation does not certify Garmin Explore/Connect import or a physical
  navigator's course geometry.

## Verification evidence and coverage limits

The F01 test module covers exact byte round-trips, original coordinate
lexical precision, detached tree behavior, incorrect namespace/root,
DOCTYPE rejection, byte/node/depth ceilings, missing strict-schema
configuration, explicit local XSD usage, and malformed XML. The F01–F03
integration suite verifies immutable source bytes across spatial, DEM and
terrain processing.

These tests demonstrate the documented cases; they do not establish
universal compatibility with every GPX producer, Garmin extension structure,
or device workflow.

## Implementation status

**Implemented and merged into `main`.** The original F01 specification was
followed by its implementation (PR #5) and F01–F03 integration tests (PR #9).
The earlier statement that F01 had not been implemented is obsolete.

## References

- Source: `src/gpx_pipeline/interoperability.py`
- Public exports: `src/gpx_pipeline/__init__.py`
- Tests: `tests/test_f01_interoperability.py`
- Integration tests: `tests/integration/test_f01_f03_end_to_end.py`
- GPX standard: https://www.topografix.com/gpx/1/1/
- Schema provenance: [F08 XSD provenance](../f08-schema-provenance.md)
