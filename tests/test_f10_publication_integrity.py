"""Fault-injection regressions for safe publication of GPX deliverables."""

import sys
from pathlib import Path

import pytest

import gpx_pipeline.output as output
from gpx_pipeline.output import OutputError, publish_outputs


ARTIFACTS = {"analytical/dataset.json": b'{"ok":true}\n'}


def publish(destination):
    """Publish a small synthetic output package."""
    return publish_outputs(
        destination, ARTIFACTS, command="analyze",
        inputs={"source": "a" * 64},
    )


def assert_clean(parent, target):
    """A failed publication must not leave staged or final artifacts."""
    assert not target.exists()
    assert not list(parent.glob(".gpx-stage-*"))


def test_write_failure_removes_stage(tmp_path, monkeypatch):
    original = Path.open

    def fail_write(path, mode="r", *args, **kwargs):
        if mode == "xb" and ".gpx-stage-" in str(path):
            raise OSError("simulated disk write failure")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_write)
    dest = tmp_path / "result"
    with pytest.raises(OutputError, match="Failed to publish"):
        publish(dest)
    assert_clean(tmp_path, dest)


def test_corrupt_staged_readback_rejected(tmp_path, monkeypatch):
    original = Path.read_bytes

    def corrupt_readback(path):
        data = original(path)
        if ".gpx-stage-" in str(path) and path.name == "dataset.json":
            return data + b"corruption"
        return data

    monkeypatch.setattr(Path, "read_bytes", corrupt_readback)
    dest = tmp_path / "result"
    with pytest.raises(OutputError, match="Output integrity failure"):
        publish(dest)
    assert_clean(tmp_path, dest)


def test_final_publication_failure_removes_stage(tmp_path, monkeypatch):
    def fail_publish(staging, target):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(output, "_publish_without_replace", fail_publish)
    dest = tmp_path / "result"
    with pytest.raises(OutputError, match="Failed to publish"):
        publish(dest)
    assert_clean(tmp_path, dest)


def test_destination_created_during_staging_preserved(tmp_path, monkeypatch):
    original = output._publish_without_replace

    def competing_publication(staging, target):
        target.mkdir()
        (target / "owner.txt").write_text("other process")
        return original(staging, target)

    monkeypatch.setattr(
        output, "_publish_without_replace", competing_publication,
    )
    dest = tmp_path / "result"
    with pytest.raises(OutputError, match="Failed to publish"):
        publish(dest)
    assert (dest / "owner.txt").read_text() == "other process"
    assert not (dest / "manifest.json").exists()
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_destination_preexists_and_is_never_overwritten(tmp_path):
    dest = tmp_path / "result"
    dest.mkdir()
    (dest / "owner.txt").write_text("existing")
    with pytest.raises(OutputError, match="already exists"):
        publish(dest)
    assert (dest / "owner.txt").read_text() == "existing"
    assert not list(tmp_path.glob(".gpx-stage-*"))


@pytest.mark.parametrize("name", [
    "../escape.gpx", "/absolute.gpx", "manifest.json", ".",
])
def test_unsafe_artifact_paths_rejected_before_staging(tmp_path, name):
    with pytest.raises(OutputError, match="Invalid output path"):
        publish_outputs(
            tmp_path / "result", {name: b"data"},
            command="analyze", inputs={},
        )
    assert_clean(tmp_path, tmp_path / "result")


def test_staging_creation_failure_is_controlled(tmp_path, monkeypatch):
    def fail_mkdtemp(*args, **kwargs):
        raise OSError("simulated temp directory failure")

    monkeypatch.setattr(output.tempfile, "mkdtemp", fail_mkdtemp)
    dest = tmp_path / "result"
    with pytest.raises(OutputError, match="Failed to create output staging"):
        publish(dest)
    assert_clean(tmp_path, dest)


def test_missing_parent_rejected_without_staging(tmp_path):
    with pytest.raises(OutputError, match="parent directory"):
        publish(tmp_path / "missing" / "result")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux no-replace syscall")
def test_atomic_noreplace_preserves_competing_empty_directory(tmp_path):
    """Even an empty competitor must never be replaced by a rename."""
    staging = tmp_path / "staged"
    staging.mkdir()
    (staging / "payload").write_text("new")
    destination = tmp_path / "result"
    destination.mkdir()
    with pytest.raises(OSError):
        output._publish_without_replace(staging, destination)
    assert staging.exists()
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
