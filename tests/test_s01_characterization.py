"""Independent GPX-01..05 oracles for approved S01-CHR v1.0.0.

Each CHRV scenario has an independent XML fixture and assertion. These tests
require the pinned production schemas and never claim downstream L3/L4 PASS.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from gpx_pipeline.characterization import characterize_gpx
from gpx_pipeline.interoperability import GPXLimits

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs/stage01/input-characterization/S01-CHR-REPORT.schema.json").read_text())
GPX = "http://www.topografix.com/GPX/1/1"
TPX = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
TPX2 = "http://www.garmin.com/xmlschemas/TrackPointExtension/v2"


def source(body):
    return f'<gpx xmlns="{GPX}" version="1.1" creator="CHRV">{body}</gpx>'.encode()


def pt(index, *, ele=None, time=None, extension="", name=""):
    return (f'<trkpt lat="{13 + index / 10000:.6f}" lon="{-86 - index / 10000:.6f}">'
            + (f"<ele>{ele}</ele>" if ele is not None else "")
            + (f"<time>{time}</time>" if time else "")
            + (f"<name>{name}</name>" if name else "")
            + extension + "</trkpt>")


def track(points=(), *, name=None, segments=None):
    if segments is None:
        segments = [points]
    return ("<trk>" + (f"<name>{name}</name>" if name is not None else "")
            + "".join("<trkseg>" + "".join(s) + "</trkseg>" for s in segments)
            + "</trk>")


def route(points, *, name=None):
    return ("<rte>" + (f"<name>{name}</name>" if name else "")
            + "".join(f'<rtept lat="13.{i:02}" lon="-86"/>' for i in points)
            + "</rte>")


def vendor(version=1, *, hr="120", cad="70", atemp="20"):
    ns = TPX if version == 1 else TPX2
    return (f'<extensions><tp:TrackPointExtension xmlns:tp="{ns}">'
            + (f"<tp:atemp>{atemp}</tp:atemp>" if atemp is not None else "")
            + (f"<tp:hr>{hr}</tp:hr>" if hr is not None else "")
            + (f"<tp:cad>{cad}</tp:cad>" if cad is not None else "")
            + "</tp:TrackPointExtension></extensions>")


def report(data, **kwargs):
    result = characterize_gpx(data, **kwargs)
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(result), key=lambda e: e.json_path)
    assert not errors, [(e.json_path, e.message) for e in errors[:5]]
    return result


def exact(result, profile):
    assert result["report_kind"] == "CHARACTERIZATION"
    assert (result["classification"]["status"], result["classification"]["resolved_profile"]) == ("SINGLE", profile)


def test_chrv_001_telemetry():
    r = report(source(track([
        pt(0, ele=100, time="2026-10-30T01:00:00Z", extension=vendor()),
        pt(1, ele=102, time="2026-10-30T01:01:00Z")])))
    exact(r, "GPX-01")
    assert all(r["features"][0]["coverage"][x]["valid"] == 1 for x in ("hr", "cad", "atemp"))


def test_chrv_002_static_track():
    r = report(source(track([pt(0, ele=100), pt(1, ele=101)], name="Summit")))
    exact(r, "GPX-02")
    assert r["capabilities"]["trk:0:temporal_L3"]["state"] == "UNAVAILABLE"


def test_chrv_003_2d_route():
    r = report(source(route([0, 1], name="Plan")))
    exact(r, "GPX-03")
    assert r["capabilities"]["rte:0:grade"]["state"] == "UNAVAILABLE"


def test_chrv_004_privacy_limit():
    r = report(source(track([pt(0, ele=100), pt(1, ele=101)])))
    exact(r, "GPX-04")
    assert r["provenance"]["privacy_status"] == "NOT_CERTIFIED"
    assert r["classification"]["intent_basis"] == "UNKNOWN"


def test_chrv_005_bare_geometry():
    r = report(source(route([0, 1])))
    exact(r, "GPX-05")
    assert r["field_coverage"]["route_points"]["ele"]["status"] == "ABSENT"


def test_chrv_006_partial_elevation():
    r = report(source(track([pt(0, ele=100), pt(1), pt(2, ele=102)], name="Partial")))
    c = r["features"][0]["coverage"]["ele"]
    assert (c["eligible"], c["present"], c["ratio"], c["status"]) == (3, 2, 2/3, "PARTIAL")
    assert r["features"][0]["matches"][1]["result"] == "PARTIAL"


def test_chrv_007_partial_timestamps():
    r = report(source(track([pt(0, time="2026-10-30T01:00:00Z"),
                             pt(1, time="2026-10-30T01:01:00Z"), pt(2)])))
    assert r["features"][0]["coverage"]["time"]["status"] == "PARTIAL"
    assert r["capabilities"]["trk:0:temporal_L3"]["state"] == "PARTIALLY_ELIGIBLE"


def test_chrv_008_segment_boundaries():
    r = report(source(track(segments=[[], [pt(0)], [pt(1), pt(2)]])))
    assert (r["inventory"]["track_segments"], r["inventory"]["empty_segments"],
            r["inventory"]["singleton_segments"]) == (3, 1, 1)


def test_chrv_009_route_only():
    r = report(source(route([0, 1], name="Route")))
    assert r["inventory"]["tracks"] == 0 and r["inventory"]["route_points"] == 2
    assert r["field_coverage"]["track_points"]["ele"]["status"] == "NOT_APPLICABLE"


def test_chrv_010_waypoints_only():
    r = report(source('<wpt lat="13" lon="-86"/><wpt lat="13.01" lon="-86"/>'))
    assert r["inventory"]["waypoints"] == 2
    assert r["classification"]["status"] == "UNCLASSIFIED"


def test_chrv_011_empty():
    r = report(source(""))
    assert r["classification"]["status"] == "UNCLASSIFIED"
    assert r["field_coverage"]["track_points"]["time"]["ratio"] is None


def test_chrv_012_singleton():
    r = report(source(track(segments=[[pt(0)], []])))
    assert r["inventory"]["singleton_segments"] == 1
    assert not r["features"][0]["has_usable_line"]


@pytest.mark.parametrize("version", (1, 2))
def test_chrv_013_garmin_versions(version):
    r = report(source(track([pt(0, ele=100, extension=vendor(version)), pt(1, ele=101)])))
    assert r["admission"]["vendor_status"] == "PASS"
    assert r["features"][0]["coverage"]["hr"]["valid"] == 1
    assert any("TrackPointExtension/v"+str(version) in v["namespace_uri"] for v in r["extensions"])


def test_chrv_014_unknown_extension():
    unknown = '<extensions><u:data xmlns:u="urn:chrv:unknown">original</u:data></extensions>'
    b = source(track([pt(0, extension=unknown), pt(1)]))
    r = report(b)
    assert r["admission"]["vendor_status"] == "INDETERMINATE"
    assert any(not x["recognized"] for x in r["extensions"])
    assert b.find(b"original") >= 0


def test_chrv_015_antimeridian():
    b = source('<rte><rtept lat="10" lon="179.9"/><rtept lat="10" lon="-179.9"/></rte>')
    r = report(b)
    assert r["summary_evidence"]["antimeridian_status"] == "CROSSING"
    extent = [d for d in r["diagnostics"] if d["code"] == "COORDINATE_EXTENT"]
    assert any("conservative_longitude_intervals=[179.900000000,180);[-180,-179.900000000]" in x for x in extent[0]["evidence"])
    assert r["features"][0]["has_usable_line"]


def test_chrv_016_vertical_datum_unknown():
    r = report(source(track([pt(0, ele=10), pt(1, ele=12)])))
    assert r["reference_evidence"]["vertical_reference"] == "UNKNOWN"
    assert r["reference_evidence"]["geoid_model"] is None


def test_chrv_017_bad_coordinates():
    r = report(source('<rte><rtept lat="91" lon="-86"/></rte>'))
    assert r["report_kind"] == "ADMISSION_FAILURE"
    assert "classification" not in r
    assert r["admission"]["gpx_xsd_status"] == "FAIL"


def test_chrv_018_mixed_and_ambiguous():
    r = report(source(track([pt(0, ele=100), pt(1, ele=102)], name="Elevated") +
                      track([pt(2), pt(3)], name="2D")))
    assert r["classification"]["status"] == "MIXED"
    a = report(source(track([pt(0, ele=100), pt(1)])))
    assert a["classification"]["status"] == "AMBIGUOUS"
    assert len(a["classification"]["candidate_profiles"]) >= 2


def test_chrv_019_declaration_conflict():
    r = report(source(track([pt(0, ele=100), pt(1, ele=101)], name="Static")),
               declared_profile="GPX-01")
    assert r["classification"]["status"] == "DECLARED_CONFLICT"
    assert r["classification"]["resolved_profile"] is None


def test_chrv_020_determinism():
    b = source(track([pt(0, ele=100), pt(1, ele=101)], name="Repeat"))
    assert report(b) == report(b)
    assert report(b)["source"]["source_sha256"] == sha256(b).hexdigest()


def test_chrv_021_source_preservation(tmp_path):
    b = source(track([pt(0), pt(500), pt(1)]))
    path = tmp_path / "outlier.gpx"
    path.write_bytes(b)
    r = report(path)
    assert path.read_bytes() == b
    assert r["inventory"]["track_points"] == 3


def test_chrv_022_large_streaming_and_limits(tmp_path):
    b = source(track([pt(i, ele=i) for i in range(1200)], name="Long"))
    p = tmp_path / "large.gpx"
    p.write_bytes(b)
    r = report(p, limits=GPXLimits(max_bytes=1_000_000))
    assert r["resource_metrics"]["parser_mode"] == "STREAMING"
    assert r["inventory"]["track_points"] == 1200
    fail = report(p, limits=GPXLimits(max_bytes=100))
    assert fail["report_kind"] == "ADMISSION_FAILURE"
    assert fail["admission"]["resource_status"] == "FAIL"


def test_chrv_023_truncated_xml():
    r = report(source('<trk><trkseg><trkpt lat="13" lon="-86"/>')[:-6])
    assert r["report_kind"] == "ADMISSION_FAILURE"
    assert r["admission"]["xml_status"] == "FAIL"


def test_chrv_024_known_invalid_extension():
    bad = vendor(hr="NOT_AN_INTEGER")
    r = report(source(track([pt(0, extension=bad), pt(1)])))
    assert r["report_kind"] == "ADMISSION_FAILURE"
    assert r["admission"]["vendor_status"] == "FAIL"
    assert "classification" not in r


def test_exv_preservation_and_no_mutation(tmp_path):
    b = source(track([pt(0, ele=200), pt(5, ele=350), pt(1, ele=250)], name="Unsafe"))
    p = tmp_path / "source.gpx"
    p.write_bytes(b)
    result = report(p)
    assert p.read_bytes() == b
    assert result["report_kind"] == "CHARACTERIZATION"
    assert not any(k in result for k in ("corrected_gpx", "synthetic_points", "export"))
    assert result["inventory"]["track_points"] == 3