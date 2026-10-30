"""EXV-001..EXV-010: approved Stage 01 negative preservation contracts.

Independent XML fixtures and source-byte assertions test exclusion invariants.
Results are characterization evidence, never L3/L4 validity or field authenticity.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

from jsonschema import Draft202012Validator
import pytest

from gpx_pipeline.characterization import characterize_gpx


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs/stage01/input-characterization/S01-CHR-REPORT.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
NS = "http://www.topografix.com/GPX/1/1"
EXPECTED_KIND = "CHARACTERIZATION"


def document(body: str) -> bytes:
    """Preserve whitespace, lexical coordinate precision and XML comments."""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<gpx xmlns="{NS}" version="1.1" creator="EXV-contract">\n'
            f'<!-- source must remain untouched -->\n{body}\n</gpx>\n').encode("utf-8")


def point(latitude: str, longitude: str, *, elevation: str | None = None,
          timestamp: str | None = None, extension: str = "") -> str:
    return (f'<trkpt lat="{latitude}" lon="{longitude}">'
            + (f'<ele>{elevation}</ele>' if elevation is not None else "")
            + (f'<time>{timestamp}</time>' if timestamp is not None else "")
            + extension + '</trkpt>')


def track(segments: list[list[str]], *, name: str | None = "Preservation") -> str:
    return ('<trk>' + (f'<name>{name}</name>' if name is not None else '')
            + ''.join('<trkseg>' + ''.join(s) + '</trkseg>' for s in segments)
            + '</trk>')


def run(source: bytes, path: Path) -> dict:
    """Assert immutable input, independent byte digest and report schema."""
    path.write_bytes(source)
    before_names = set(path.parent.iterdir())
    result = characterize_gpx(path)
    assert result["report_kind"] == EXPECTED_KIND, result.get("diagnostics")
    assert path.read_bytes() == source
    assert set(path.parent.iterdir()) == before_names
    assert result["source"]["source_sha256"] == sha256(source).hexdigest()
    assert result["source"]["bytes"] == len(source)
    errors = list(VALIDATOR.iter_errors(result))
    assert not errors, [(e.json_path, e.message) for e in errors[:3]]
    # An accepted characterization must never contain a replacement GPX.
    assert not ({"corrected_gpx", "repaired_gpx", "export", "navigation",
                 "synthetic_points", "analytical_dataset"} & result.keys())
    return result


def test_exv_001_source_bytes_unchanged(tmp_path):
    """EXV-001 (EXC-001, INV-001): preserve exact source, not just geometry."""
    data = document(track([[point("13.0000000", "-86.0000000", elevation="00012.50"),
                            point("13.0001000", "-86.0001000", elevation="12.5000")]]))
    first = run(data, tmp_path / "source.gpx")
    second = run(data, tmp_path / "source.gpx")
    assert first == second == characterize_gpx(data)
    assert first["inventory"]["track_points"] == 2


def test_exv_002_spatial_outliers_never_removed(tmp_path):
    """EXV-002 (EXC-010, INV-002): retain a conspicuous spatial spike."""
    data = document(track([[point("13.0000", "-86.0000"),
                            point("13.8000", "-85.2000"),
                            point("13.0001", "-86.0001")]]))
    result = run(data, tmp_path / "spike.gpx")
    assert result["inventory"]["track_points"] == 3
    assert result["features"][0]["point_count"] == 3
    assert any(d["code"] == "COORDINATE_EXTENT" and
               any("13.800000000" in e for e in d["evidence"])
               for d in result["diagnostics"])


def test_exv_003_temporal_regression_not_reordered(tmp_path):
    """EXV-003 (EXC-005, INV-003): chronology remains source-ordered."""
    times = ["2026-10-30T03:00:00Z", "2026-10-30T02:59:00Z",
             "2026-10-30T03:01:00Z"]
    data = document(track([[point("13.0000", "-86.0000", timestamp=times[0]),
                            point("13.0001", "-86.0001", timestamp=times[1]),
                            point("13.0002", "-86.0002", timestamp=times[2])]]))
    result = run(data, tmp_path / "regression.gpx")
    assert result["field_coverage"]["track_points"]["time"]["valid"] == 3
    assert result["inventory"]["track_points"] == len(times)
    # L3 may later reject the regression; characterization must not silently repair it.
    assert all(cap["state"] not in {"PASS", "FAIL"}
               for cap in result["capabilities"].values())


def test_exv_004_missing_observations_not_interpolated(tmp_path):
    """EXV-004 (EXC-004, INV-004): a missing middle value remains missing."""
    data = document(track([[point("13.00", "-86.00", elevation="100",
                                  timestamp="2026-10-30T03:00:00Z"),
                            point("13.01", "-86.01"),
                            point("13.02", "-86.02", elevation="103",
                                  timestamp="2026-10-30T03:02:00Z")]]))
    result = run(data, tmp_path / "missing.gpx")
    for key in ("ele", "time"):
        cov = result["field_coverage"]["track_points"][key]
        assert (cov["eligible"], cov["present"], cov["valid"]) == (3, 2, 2)
        assert cov["status"] == "PARTIAL"
    assert result["inventory"]["track_points"] == 3
    assert '<trkpt lat="13.01" lon="-86.01"></trkpt>' in data.decode()


@pytest.mark.parametrize("segments,expected_suitable", [
    ([[point("13.00", "-86.00")], [point("13.01", "-86.01")]], False),
    ([[point("13.00", "-86.00"), point("13.01", "-86.01")],
      [point("13.02", "-86.02"), point("13.03", "-86.03")]], True),
], ids=("two-singleton-segments", "two-distinct-lines"))
def test_exv_005_segments_not_merged(tmp_path, segments, expected_suitable):
    """EXV-005 (EXC-006, INV-003): never bridge or merge track segments."""
    data = document(track(segments))
    result = run(data, tmp_path / "segments.gpx")
    assert result["inventory"]["track_segments"] == 2
    assert result["features"][0]["segment_count"] == 2
    assert result["summary_evidence"]["segment_boundaries_preserved"] is True
    assert result["summary_evidence"]["geodesic_line_suitable"] is expected_suitable
    assert result["features"][0]["point_count"] == sum(map(len, segments))
    if not expected_suitable:
        assert result["classification"]["status"] == "UNCLASSIFIED"


def test_exv_006_extreme_elevations_never_rewritten(tmp_path):
    """EXV-006 (EXC-007, INV-001): do not correct anomalous elevations."""
    heights = ("-500.000", "8000.000", "-501.000")
    data = document(track([[point("13.00", "-86.00", elevation=heights[0]),
                            point("13.01", "-86.01", elevation=heights[1]),
                            point("13.02", "-86.02", elevation=heights[2])]]))
    result = run(data, tmp_path / "elevation.gpx")
    assert result["field_coverage"]["track_points"]["ele"]["valid"] == 3
    assert result["reference_evidence"]["vertical_reference"] == "UNKNOWN"
    assert all(f'<ele>{height}</ele>'.encode() in data for height in heights)
    assert result["provenance"]["origin"] == "UNKNOWN"


def test_exv_007_opaque_extensions_not_removed(tmp_path):
    """EXV-007 (EXC-003, INV-005): unknown vendor content retained as opaque."""
    vendor = ('<extensions><u:payload xmlns:u="urn:exv:private" u:code="001">'
              'keep&amp;verify</u:payload></extensions>')
    data = document(track([[point("13.00", "-86.00", extension=vendor),
                            point("13.01", "-86.01")]]))
    result = run(data, tmp_path / "vendor.gpx")
    assert result["admission"]["vendor_status"] == "INDETERMINATE"
    assert any(x["namespace_uri"] == "urn:exv:private" and
               x["recognized"] is False for x in result["extensions"])
    assert vendor.encode() in data
    assert result["provenance"]["privacy_status"] == "NOT_CERTIFIED"


def test_exv_008_no_navigation_outputs(tmp_path):
    """EXV-008 (EXC-013, INV-010): characterize emits only JSON stdout."""
    executable = shutil.which("gpx-pipeline")
    assert executable, "installed CLI entrypoint is a test prerequisite"
    data = document(track([[point("13.00", "-86.00", elevation="100"),
                            point("13.01", "-86.01", elevation="101")]]))
    src = tmp_path / "navigation-input.gpx"
    src.write_bytes(data)
    before = set(tmp_path.iterdir())
    completed = subprocess.run([executable, "characterize", str(src)],
                               capture_output=True, text=True, check=False, timeout=30)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["report_kind"] == EXPECTED_KIND
    assert not list(VALIDATOR.iter_errors(result))
    assert set(tmp_path.iterdir()) == before
    assert src.read_bytes() == data
    assert not any(x.suffix.lower() in {".gpx", ".fit", ".tcx"} for x in
                   (set(tmp_path.iterdir()) - before))


def test_exv_009_metrics_remain_diagnostic_only(tmp_path):
    """EXV-009 (EXC-015, INV-005): no performance product or quality verdict."""
    data = document(track([[point("13.00", "-86.00", elevation="100",
                                  timestamp="2026-10-30T03:00:00Z"),
                            point("13.01", "-86.01", elevation="102",
                                  timestamp="2026-10-30T03:01:00Z"),
                            point("13.02", "-86.02", elevation="103",
                                  timestamp="2026-10-30T03:02:00Z")]]))
    result = run(data, tmp_path / "diagnostics.gpx")
    assert result["capabilities"]["trk:0:temporal_L3"]["state"] == "ELIGIBLE_FOR_VALIDATION"
    assert result["capabilities"]["trk:0:kinematic_L4"]["state"] == "ELIGIBLE_FOR_VALIDATION"
    assert all(c["state"] in {"ELIGIBLE_FOR_VALIDATION", "PARTIALLY_ELIGIBLE",
                               "UNAVAILABLE", "INDETERMINATE"}
               for c in result["capabilities"].values())
    assert not ({"performance", "pace", "grade_percent", "speed_m_s",
                 "time_in_motion", "moving_distance_m"} & result.keys())
    assert all(d["requirement_id"].startswith("CHR-") for d in result["diagnostics"])


def test_exv_010_uncertainty_and_missingness_explicit(tmp_path):
    """EXV-010 (INV-006, INV-007): no invented datum, privacy or coverage."""
    data = document(track([[point("13.00", "-86.00", elevation="100"),
                            point("13.01", "-86.01"),
                            point("13.02", "-86.02", elevation="105")]], name=None))
    result = run(data, tmp_path / "uncertain.gpx")
    cov = result["field_coverage"]["track_points"]
    assert (cov["ele"]["status"], cov["ele"]["valid"], cov["ele"]["eligible"]) == ("PARTIAL", 2, 3)
    assert (cov["time"]["status"], cov["time"]["present"]) == ("ABSENT", 0)
    assert result["reference_evidence"]["vertical_reference"] == "UNKNOWN"
    assert result["reference_evidence"]["geoid_model"] is None
    assert result["provenance"]["origin"] == "UNKNOWN"
    assert result["provenance"]["privacy_status"] == "NOT_CERTIFIED"
    assert result["classification"]["status"] != "SINGLE"
    assert result["field_coverage"]["route_points"]["ele"]["ratio"] is None


@pytest.mark.parametrize("malformed,expected_field", [
    (b"<gpx", "xml_status"),
    (document(track([[point("91", "-86"), point("13", "-86")]])), "gpx_xsd_status"),
], ids=("truncated-xml", "invalid-coordinate"))
def test_exclusion_failure_path_never_repairs_input(tmp_path, malformed, expected_field):
    """Admission must reject bad input rather than repair or publish a profile."""
    path = tmp_path / "rejected.gpx"
    path.write_bytes(malformed)
    result = characterize_gpx(path)
    assert path.read_bytes() == malformed
    assert result["report_kind"] == "ADMISSION_FAILURE"
    assert result["admission"][expected_field] == "FAIL"
    assert "classification" not in result and "capabilities" not in result
    assert not list(VALIDATOR.iter_errors(result))
    assert list(tmp_path.iterdir()) == [path]

