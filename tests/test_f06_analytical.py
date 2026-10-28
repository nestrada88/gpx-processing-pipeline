"""F06 analytical dataset linkage and preservation regression tests."""

import json

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import (
    AnalyticalDatasetError, analytical_json, build_analytical_dataset,
)
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.waypoints import enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"


def fixture():
    """Provide timed track segments and recorded, distinct elevations."""
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="test">'
        '<wpt lat="12" lon="-86"><name>Checkpoint</name></wpt>'
        '<trk><trkseg>'
        '<trkpt lat="12" lon="-86"><ele>999</ele>'
        '<time>2026-01-01T00:00:00Z</time></trkpt>'
        '<trkpt lat="12" lon="-85.999"><ele>998</ele>'
        '<time>2026-01-01T00:01:00Z</time></trkpt>'
        '</trkseg><trkseg>'
        '<trkpt lat="13" lon="-86"><ele>997</ele></trkpt>'
        '</trkseg></trk></gpx>'
    ).encode("utf-8")
    document = parse_gpx(xml, strict=False)
    provenance = DEMProvenance(
        "synthetic", "EPSG:4326", "local-datum",
        "m", (1, 1), "nearest", None,
    )
    samples = (
        DEMSample("waypoint", 0, None, 0, 100., "ok"),
        DEMSample("track", 0, 0, 0, 110., "ok"),
        DEMSample("track", 0, 0, 1, 120., "ok"),
        DEMSample("track", 0, 1, 0, None, "missing"),
    )
    return document, DEMResult(samples, provenance)


def test_complete_assembly_and_recorded_vs_derived():
    """Assemble upstream outputs with provenance and no source mutation."""
    document, dem = fixture()
    before = serialize_gpx(document)
    catalog = enrich_waypoints(
        document, categories={0: "checkpoint"}, checkpoints={0: 1}
    )
    product = build_analytical_dataset(document, dem=dem, waypoints=catalog)
    assert [s.point_count for s in product.segments] == [2, 1]
    assert product.segments[0].terrain_complete
    assert not product.segments[1].terrain_complete
    first, second, third, waypoint = product.points
    assert first.recorded_elevation_text == "999"
    assert first.dem_elevation_m == 110.
    assert second.dem_elevation_m == 120.
    assert second.grade_percent > 0
    assert second.elapsed_from_previous_s == 60
    assert second.observed_speed_m_s > 0
    assert third.dem_status == "missing"
    assert third.cumulative_distance_m == 0
    assert waypoint.kind == "waypoint"
    assert waypoint.dem_elevation_m == 100.
    assert product.waypoint_catalog.entries[0].checkpoint_order == 1
    assert product.dem_vertical_datum == "local-datum"
    assert serialize_gpx(document) == before


def test_optional_enrichment_and_deterministic_json():
    """Absent optional stages yield nulls and reproducible JSON bytes."""
    document, _ = fixture()
    first = build_analytical_dataset(document)
    second = build_analytical_dataset(document)
    assert analytical_json(first) == analytical_json(second)
    parsed = json.loads(analytical_json(first))
    assert parsed["schema_version"] == "1.0.0"
    assert "DEM_NOT_SUPPLIED" in parsed["diagnostics"]
    assert parsed["points"][0]["dem_elevation_m"] is None
    assert parsed["points"][1]["observed_speed_m_s"] is not None


def test_waypoint_catalog_must_match_source():
    """Do not accept enrichment labels from a different GPX document."""
    document, _ = fixture()
    catalog = enrich_waypoints(document)
    from dataclasses import replace

    foreign = replace(catalog, entries=(
        replace(catalog.entries[0], name="Other"),
    ))
    with pytest.raises(AnalyticalDatasetError, match="source mismatch"):
        build_analytical_dataset(document, waypoints=foreign)


def test_temporal_can_be_skipped():
    """Planned tracks may lack recorded activity timing."""
    document, _ = fixture()
    product = build_analytical_dataset(document, include_temporal=False)
    assert "TEMPORAL_NOT_COMPUTED" in product.diagnostics
    assert all(s.timing_complete is None for s in product.segments)
    assert all(p.observed_speed_m_s is None for p in product.points)
