"""Installed CLI smoke contracts for S01-CHR's separate admission path."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


NS = "http://www.topografix.com/GPX/1/1"


def _input(tmp_path, *, extension=""):
    path = tmp_path / "source.gpx"
    path.write_text(
        f'<gpx xmlns="{NS}" version="1.1" creator="s01-cli">'
        "<trk><name>Named static track</name><trkseg>"
        '<trkpt lat="13" lon="-86"><ele>100</ele></trkpt>'
        '<trkpt lat="13.01" lon="-86"><ele>101</ele></trkpt>'
        f"</trkseg></trk>{extension}</gpx>", encoding="utf-8",
    )
    return path


def _cli(*args):
    executable = shutil.which("gpx-pipeline")
    assert executable is not None, "Installed CLI expected"
    return subprocess.run(
        [executable, *(str(arg) for arg in args)],
        capture_output=True, text=True, check=False, timeout=30,
    )


def test_cli_characterize_gpx02_json_and_preservation(tmp_path):
    src = _input(tmp_path)
    original = src.read_bytes()
    r = _cli("characterize", src)
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout)
    assert result["report_kind"] == "CHARACTERIZATION"
    assert result["classification"]["resolved_profile"] == "GPX-02"
    assert src.read_bytes() == original
    assert not list(tmp_path.glob("*.json"))


def test_cli_characterize_unknown_extension_but_f08_validate_rejects(tmp_path):
    other = '<extensions><u:data xmlns:u="urn:s01:opaque">source</u:data></extensions>'
    src = _input(tmp_path, extension=other)
    original = src.read_bytes()
    characterization = _cli("characterize", src)
    assert characterization.returncode == 0, characterization.stderr
    assert json.loads(characterization.stdout)["admission"]["vendor_status"] == "INDETERMINATE"
    production = _cli("validate", src, "--format", "json")
    assert production.returncode == 3
    assert src.read_bytes() == original


def test_cli_characterize_declared_conflict(tmp_path):
    src = _input(tmp_path)
    r = _cli("characterize", src, "--declared-profile", "GPX-01")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["classification"]["status"] == "DECLARED_CONFLICT"


@pytest.mark.parametrize("kind,exit_code", [("invalid", 3), ("oversize", 4)])
def test_cli_characterize_admission_failure(tmp_path, kind, exit_code):
    src = _input(tmp_path)
    if kind == "invalid":
        src.write_bytes(b"<gpx")
        r = _cli("characterize", src)
    else:
        r = _cli("characterize", src, "--max-input-bytes", "90")
    assert r.returncode == exit_code
    result = json.loads(r.stdout)
    assert result["report_kind"] == "ADMISSION_FAILURE"
    assert "classification" not in result
