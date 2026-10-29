"""NV-19B fail-closed publication under platform and durability failures.

Non-native Windows behavior is simulated, NOT claimed to be Windows-verified.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import gpx_pipeline.output as output
from gpx_pipeline.output import OutputError, publish_outputs


def _publish(destination):
    """Stage an immutable test payload plus integrity manifest."""
    return publish_outputs(
        destination,
        {"navigation/route.gpx": b"<gpx/>"},
        command="export",
        inputs={"source": "f" * 64},
    )


def _assert_no_stage(parent):
    """Discard staging directories even when publication fails."""
    assert not list(parent.glob(".gpx-stage-*"))


def test_unsupported_platform_fails_closed_before_target_created(
    tmp_path, monkeypatch,
):
    """Unknown OS must never use a non-atomic, replacing publication fallback."""
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform="freebsd"))
    target = tmp_path / "delivery"
    with pytest.raises(OutputError, match="Atomic no-replace publication unavailable"):
        _publish(target)
    assert not target.exists()
    _assert_no_stage(tmp_path)


def test_linux_without_renameat2_never_publishes(tmp_path, monkeypatch):
    """Missing kernel/libc API must not silently fall back to unsafe rename."""
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(
        output.ctypes, "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    target = tmp_path / "delivery"
    with pytest.raises(OutputError, match="Atomic no-replace publication unavailable"):
        _publish(target)
    assert not target.exists()
    _assert_no_stage(tmp_path)


def test_windows_rename_error_preserves_competing_directory(
    tmp_path, monkeypatch,
):
    """Simulated Windows collision: a failed rename cannot replace other work.

    This does not establish Windows filesystem guarantees on a Linux CI runner.
    """
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform="win32"))
    before_rename = Path.rename

    def reject_collision(staging, target):
        target.mkdir()
        (target / "owner.txt").write_text("competing process")
        raise FileExistsError("simulated Windows rename collision")

    monkeypatch.setattr(Path, "rename", reject_collision)
    target = tmp_path / "delivery"
    with pytest.raises(OutputError, match="Failed to publish outputs"):
        _publish(target)
    assert (target / "owner.txt").read_text() == "competing process"
    assert not (target / "manifest.json").exists()
    _assert_no_stage(tmp_path)
    monkeypatch.setattr(Path, "rename", before_rename)


def test_fsync_failure_cleans_staging_and_never_publishes(
    tmp_path, monkeypatch,
):
    """Durability failures invalidate the whole output transaction."""
    def fail_sync(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(output.os, "fsync", fail_sync)
    target = tmp_path / "delivery"
    with pytest.raises(OutputError, match="injected fsync failure"):
        _publish(target)
    assert not target.exists()
    _assert_no_stage(tmp_path)
