"""Write a complete, integrity-tracked output directory without overwrites."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Mapping


class OutputError(ValueError):
    """Represent a failed safe output publication."""


def manifest_bytes(
    artifacts: Mapping[str, bytes],
    *,
    command: str,
    inputs: Mapping[str, str],
) -> bytes:
    """Serialize deterministic input/output hashes, omitting clock timestamps."""
    record = {
        "schema_version": "1.0.0",
        "command": command,
        "inputs": dict(sorted(inputs.items())),
        "artifacts": {
            key: {"sha256": sha256(artifacts[key]).hexdigest(),
                  "bytes": len(artifacts[key])}
            for key in sorted(artifacts)
        },
    }
    return (json.dumps(
        record, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n").encode("utf-8")


def publish_outputs(
    destination: Path,
    artifacts: Mapping[str, bytes],
    *,
    command: str,
    inputs: Mapping[str, str],
) -> tuple[str, ...]:
    """Stage all files and publish a new directory, never overwrite an old one.

    A failed stage leaves no successful-looking final directory. Publishing
    uses an atomic rename where supported on the same local filesystem.
    """
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise OutputError(f"Output destination already exists: {target}")
    if not target.parent.is_dir():
        raise OutputError(f"Output parent directory does not exist: {target.parent}")
    contents = dict(artifacts)
    if not contents:
        raise OutputError("No outputs to publish")
    for relative, data in contents.items():
        path = PurePosixPath(relative)
        if (path.is_absolute() or ".." in path.parts
                or not path.parts or relative == "manifest.json"
                or any(part in {"", "."} for part in path.parts)):
            raise OutputError(f"Invalid output path: {relative}")
        if not isinstance(data, bytes):
            raise OutputError("All output payloads must be bytes")
    contents["manifest.json"] = manifest_bytes(
        contents, command=command, inputs=inputs,
    )
    staging = Path(tempfile.mkdtemp(prefix=".gpx-stage-", dir=target.parent))
    try:
        for relative, data in sorted(contents.items()):
            path = staging.joinpath(*PurePosixPath(relative).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if sha256(path.read_bytes()).digest() != sha256(data).digest():
                raise OutputError(f"Output integrity failure: {relative}")
        if target.exists() or target.is_symlink():
            raise OutputError("Output destination appeared during staging")
        staging.rename(target)
        return tuple(sorted(contents))
    except (OSError, ValueError) as exc:
        if isinstance(exc, OutputError):
            raise
        raise OutputError(f"Failed to publish outputs: {exc}") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging)
