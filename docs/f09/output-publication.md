# F09 — Deterministic Output Publication

[← F09 overview](../F09-PIPELINE-ORCHESTRATION-CLI.md)

Implementation: [`src/gpx_pipeline/output.py`](../../src/gpx_pipeline/output.py); integration tests: [`tests/test_f09_pipeline.py`](../../tests/test_f09_pipeline.py).

## Public API

```python
manifest_bytes(
    artifacts: Mapping[str, bytes],
    *,
    command: str,
    inputs: Mapping[str, str],
) -> bytes

publish_outputs(
    destination: Path,
    artifacts: Mapping[str, bytes],
    *,
    command: str,
    inputs: Mapping[str, str],
) -> tuple[str, ...]
```

`OutputError(ValueError)` denotes invalid publication configuration, safety rejection or a wrapped filesystem error. The caller must provide all artifact contents as bytes, with **relative** POSIX path keys. `publish_outputs` returns sorted published relative paths, including `manifest.json`.

## Manifest contract

The publication manifest is deterministic compact UTF-8 JSON ending in a newline. Its structure:

```json
{
  "schema_version": "1.0.0",
  "command": "analyze",
  "inputs": {"source": "<actual source SHA-256>"},
  "artifacts": {
    "analytical/dataset.json": {
      "sha256": "<actual artifact SHA-256>",
      "bytes": 123
    }
  }
}
```

The values above are schematic; actual digests and byte counts are generated from each real payload. The manifest **does not hash itself** and is excluded from its own artifact dictionary. Input fingerprint keys are sorted, artifact keys are sorted and JSON keys are sorted. No wall-clock timestamp is inserted. These hashes establish byte integrity and repeatability, not physical Garmin course integrity or authenticity of input scientific measurements.

## Publication sequence and safety properties

1. Refuse if the destination path already exists **or is a symlink**, and refuse when the destination parent is not an existing directory.
2. Refuse empty artifact mappings, non-bytes payloads, absolute artifact paths, `..` traversal, invalid path components or caller-supplied root `manifest.json` (reserved for publication metadata).
3. Generate `manifest.json` from the supplied artifacts, command and input hashes.
4. Create a uniquely named `.gpx-stage-` directory **inside the destination's parent**.
5. In sorted path order, create each necessary staged subdirectory; open output files exclusively in binary mode; write, flush and `os.fsync` each file.
6. Re-read staged files and compare their SHA-256 hashes against the source payloads.
7. Refuse if the destination appeared during staging; rename staging to the final path on the same filesystem.
8. Always clean remaining staging directory contents after success/failure; on failure, do not return a successfully published artifact set.

The implementation uses an adjacent staging directory and an atomic directory rename **where supported** by the local filesystem. It does not implement directory fsync, journaling, distributed/object-store transactions, recovery after every sudden power loss or protection from all external races; therefore avoid stronger crash-durability claims.

## Example with self-contained artifacts

```python
from pathlib import Path
from hashlib import sha256
from gpx_pipeline.output import publish_outputs

source_bytes = b"illustrative local input"
artifacts = {"reports/example.txt": b"analysis result\n"}
names = publish_outputs(
    Path("results/run-04"),
    artifacts,
    command="analyze",
    inputs={"source": sha256(source_bytes).hexdigest()},
)
assert "manifest.json" in names
assert "reports/example.txt" in names
```

Create the `results` parent directory separately before using this example; do not create `run-04` beforehand. The example illustrates publication mechanics, **not** an actual validated GPX processing run.

## Failure semantics and deterministic boundaries

`publish_outputs` raises `OutputError` on a collision, invalid relative path, unsupported payload, staging integrity mismatch or filesystem failure. F09 `run_pipeline` wraps these as `PipelineError("OUTPUT_FAILED", ...)`, mapped to CLI exit status 6. A source-processing failure before publication leaves no final output directory through this publishing function.

Outputs are deterministic for identical source and configuration under stable dependency and DEM inputs. External provider updates, platform/environment differences and different local raster bytes can affect actual upstream payloads; the publication layer itself does not normalize those inputs.

Test coverage includes no-overwrite behavior, traversal rejection, successful manifest/hash generation and run repeatability. No fresh tests were executed for this documentation.
