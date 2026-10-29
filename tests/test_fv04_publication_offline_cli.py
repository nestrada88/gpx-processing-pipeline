"""FV-04 CLI-to-filesystem repeatability, offline, and publication contracts."""

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def _source(tmp_path):
    """Construct minimal valid GPX in an immutable local fixture."""
    path = tmp_path / "source.gpx"
    path.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" '
        'version="1.1" creator="fv04">'
        '<trk><trkseg><trkpt lat="12" lon="-86"/>'
        '<trkpt lat="12.003" lon="-85.997"/></trkseg></trk></gpx>',
        encoding="utf-8",
    )
    return path


def _cli(*args):
    """Invoke the installed executable with isolated output streams."""
    exe = shutil.which("gpx-pipeline")
    assert exe, "Installed CLI is required for functional tests"
    return subprocess.run(
        [exe, *map(str, args)],
        text=True, capture_output=True, check=False, timeout=45,
    )


def _published_tree(destination):
    """Verify manifest integrity and return all payload bytes for comparison."""
    manifest_bytes = (destination / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    payloads = {}
    for relative, digest in manifest["artifacts"].items():
        contents = (destination / relative).read_bytes()
        assert digest["sha256"] == sha256(contents).hexdigest()
        assert digest["bytes"] == len(contents)
        payloads[relative] = contents
    assert set(payloads) == {
        str(path.relative_to(destination))
        for path in destination.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    return manifest_bytes, payloads


def test_two_independent_cli_runs_are_byte_deterministic(tmp_path):
    """Destination names must not leak into artifact bytes or manifests."""
    source = _source(tmp_path)
    source_before = source.read_bytes()
    first, second = (tmp_path / "first", tmp_path / "second")
    for output in (first, second):
        result = _cli(
            "analyze", source, "--output", output,
            "--forecast", "--assume-flat-grade",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(output)
        assert result.stderr == ""
    assert _published_tree(first) == _published_tree(second)
    assert json.loads((first / "manifest.json").read_bytes())["inputs"] == {
        "source": sha256(source_before).hexdigest(),
    }
    assert source.read_bytes() == source_before
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_cli_refuses_existing_symlink_without_touching_its_target(tmp_path):
    """Do not follow an existing output symlink into another directory."""
    source = _source(tmp_path)
    actual = tmp_path / "owned"
    actual.mkdir()
    marker = actual / "marker.txt"
    marker.write_text("retain", encoding="utf-8")
    link = tmp_path / "published"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks unavailable in this CI environment: {exc}")
    result = _cli("analyze", source, "--output", link)
    assert result.returncode == 6
    assert "OUTPUT_FAILED:" in result.stderr
    assert link.is_symlink()
    assert marker.read_text(encoding="utf-8") == "retain"
    assert sorted(p.name for p in actual.iterdir()) == ["marker.txt"]
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_cli_nonexistent_output_parent_fails_without_partial_artifacts(tmp_path):
    """Publication requires an existing parent; no nested output is fabricated."""
    source = _source(tmp_path)
    destination = tmp_path / "absent-parent" / "result"
    result = _cli("analyze", source, "--output", destination)
    assert result.returncode == 6
    assert "OUTPUT_FAILED:" in result.stderr
    assert not destination.parent.exists()
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_cli_invalid_xml_does_not_publish_or_modify_source(tmp_path):
    """Reject malformed XML before output stage and preserve original bytes."""
    source = _source(tmp_path)
    source.write_bytes(source.read_bytes().replace(b"</trkseg>", b""))
    previous = source.read_bytes()
    destination = tmp_path / "bad-xml-output"
    result = _cli("process", source, "--output", destination)
    assert result.returncode == 3
    assert "GPX_INVALID:" in result.stderr
    assert not destination.exists()
    assert source.read_bytes() == previous
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_local_validation_operates_with_outbound_network_calls_disabled(tmp_path):
    """A subprocess blocks socket connects before executing the actual CLI.

    This tests validate's local operation, not global proof that every possible
    command or dependency is guaranteed network-free under all configurations.
    """
    source = _source(tmp_path)
    script = (
        "import runpy, socket, sys\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('unexpected outbound network operation')\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "socket.create_connection = blocked\n"
        "sys.argv = ['gpx-pipeline', 'validate', sys.argv[1], "
        "'--format', 'json']\n"
        "runpy.run_module('gpx_pipeline.cli', run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(source)],
        capture_output=True, text=True, check=False, timeout=45,
        env=dict(os.environ),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "valid": True, "sha256": sha256(source.read_bytes()).hexdigest(),
    }
    assert result.stderr == ""
