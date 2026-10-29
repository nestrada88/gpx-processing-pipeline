"""FV-06 CLI negative contracts for observed time and unknown extensions."""

import shutil
import subprocess

import pytest


NS = "http://www.topografix.com/GPX/1/1"


def _cli(*args):
    """Exercise the installed command in a separate process."""
    executable = shutil.which("gpx-pipeline")
    assert executable, "Installed console script required"
    return subprocess.run(
        [executable, *(str(arg) for arg in args)],
        capture_output=True, text=True, check=False, timeout=30,
    )


def _source(tmp_path, times, *, extra=""):
    """Keep topology and coordinates valid while varying one input contract."""
    points = "".join(
        f'<trkpt lat="12" lon="{-86 + index * .001:.3f}">'
        f"<time>{instant}</time></trkpt>"
        for index, instant in enumerate(times)
    )
    file = tmp_path / "input.gpx"
    file.write_text(
        f'<gpx xmlns="{NS}" version="1.1" creator="fv06">'
        f"<trk><trkseg>{points}</trkseg></trk>{extra}</gpx>",
        encoding="utf-8",
    )
    return file


@pytest.mark.parametrize(
    "times",
    [
        ("2026-10-29T08:02:00Z", "2026-10-29T08:01:00Z"),
        ("2026-10-29T08:01:00Z", "2026-10-29T08:01:00Z"),
    ],
    ids=("decreasing", "duplicate"),
)
def test_cli_rejects_non_monotonic_observed_time_without_publication(
    tmp_path, times,
):
    """Chronological failures must not produce analytical artifacts."""
    source = _source(tmp_path, times)
    before = source.read_bytes()
    destination = tmp_path / "rejected"
    result = _cli("analyze", source, "--output", destination)
    assert result.returncode == 3
    assert "TEMPORAL_INVALID:" in result.stderr
    assert not destination.exists()
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_cli_rejects_calendar_invalid_timestamp_before_publication(tmp_path):
    """An impossible calendar date must not enter temporal analytics."""
    source = _source(
        tmp_path,
        ("2026-02-30T08:01:00Z", "2026-03-01T08:02:00Z"),
    )
    before = source.read_bytes()
    destination = tmp_path / "rejected"
    result = _cli("process", source, "--output", destination)
    assert result.returncode == 3
    assert "GPX_INVALID:" in result.stderr
    assert not destination.exists()
    assert source.read_bytes() == before


def test_cli_rejects_unregistered_gpx_extension_before_export(tmp_path):
    """Unknown extension content is not silently dropped from Garmin output."""
    source = _source(
        tmp_path,
        ("2026-10-29T08:01:00Z", "2026-10-29T08:02:00Z"),
        extra=(
            '<extensions><unknown:data xmlns:unknown="urn:fv06:unregistered">'
            'payload</unknown:data></extensions>'
        ),
    )
    before = source.read_bytes()
    destination = tmp_path / "no-export"
    result = _cli(
        "export", source, "--output", destination,
        "--garmin", "etrex-se",
    )
    assert result.returncode == 3
    assert "GPX_INVALID:" in result.stderr
    assert not destination.exists()
    assert source.read_bytes() == before
