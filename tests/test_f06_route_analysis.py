"""F06 route-analysis statistical reference and completeness regression tests."""

from dataclasses import replace
import json

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.route_analysis import (
    RouteAnalysisError, RouteAnalysisOptions, analyze_route,
    route_analysis_json,
)
from gpx_pipeline.waypoints import enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"


def document():
    """Create independent timed track segments, a route and checkpoint."""
    body = (
        '<wpt lat="0" lon="0"><name>CP</name></wpt>'
        '<trk><trkseg>'
        '<trkpt lat="0" lon="0"><time>2026-01-01T00:00:00Z</time></trkpt>'
        '<trkpt lat="0" lon="0.001"><time>2026-01-01T00:01:00Z</time></trkpt>'
        '<trkpt lat="0" lon="0.002"><time>2026-01-01T00:02:00Z</time></trkpt>'
        '</trkseg><trkseg><trkpt lat="1" lon="1"/>'
        '<trkpt lat="1" lon="1.001"/></trkseg></trk>'
        '<rte><rtept lat="2" lon="2"/><rtept lat="2" lon="2.001"/></rte>'
    )
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="tests">'
         f'{body}</gpx>').encode(), strict=False,
    )


def dataset(*, missing=False):
    """Return assembled F06 data with independently defined DEM heights."""
    doc = document()
    heights = [100, 110, 100, 200, 190, 50, 50]
    keys = [
        ("waypoint", 0, None, 0),
        ("track", 0, 0, 0),
        ("track", 0, 0, 1),
        ("track", 0, 0, 2),
        ("track", 0, 1, 0),
        ("track", 0, 1, 1),
        ("route", 0, None, 0),
        ("route", 0, None, 1),
    ]
    heights = [0, 100, 110, 100, 200, 190, 50, 50]
    samples = tuple(
        DEMSample(*key, None if missing and key == ("track", 0, 0, 1) else h,
                  "missing" if missing and key == ("track", 0, 0, 1) else "ok")
        for key, h in zip(keys, heights)
    )
    dem = DEMResult(samples, DEMProvenance(
        "synthetic.tif", "EPSG:4326", "local", "m",
        (1, 1), "nearest", 1.0,
    ))
    catalog = enrich_waypoints(
        doc, categories={0: "checkpoint"}, checkpoints={0: 1},
    )
    return build_analytical_dataset(doc, dem=dem, waypoints=catalog)


def test_segment_metrics_grade_categories_and_checkpoint():
    """Classify grade and preserve per-segment ascent/descent boundaries."""
    result = analyze_route(dataset())
    assert result.statistics.tracks == 1
    assert result.statistics.routes == 1
    assert result.statistics.segments == 3
    assert result.statistics.geometry_points == 7
    assert result.statistics.waypoint_count == 1
    assert [s.ascent_m for s in result.segments] == [10, 0, 0]
    assert [s.descent_m for s in result.segments] == [10, 10, 0]
    assert result.statistics.ascent_m == 10
    assert result.statistics.descent_m == 20
    assert result.segments[0].grades.uphill_edges == 1
    assert result.segments[0].grades.downhill_edges == 1
    assert result.segments[2].grades.flat_edges == 1
    assert result.checkpoints[0].checkpoint_order == 1
    assert result.checkpoints[0].nearest_vertex_m == 0
    assert result.dem_vertical_datum == "local"
    assert result.statistics.observed_elapsed_s is None  # incomplete second track


def test_missing_dem_does_not_bridge_elevation_gap():
    """Partial elevation coverage makes ascent/descent explicitly unknown."""
    result = analyze_route(dataset(missing=True))
    first = result.segments[0]
    assert first.ascent_m is None and first.descent_m is None
    assert first.elevation_coverage == pytest.approx(2 / 3)
    assert result.statistics.ascent_m is None
    assert result.statistics.elevation_coverage == pytest.approx(6 / 7)
    assert "PARTIAL_OR_UNAVAILABLE_TERRAIN" in result.diagnostics


def test_unenriched_dataset_has_unavailable_statistics():
    """Do not invent missing elevation or movement measurements."""
    doc = document()
    result = analyze_route(build_analytical_dataset(
        doc, include_temporal=False,
    ))
    assert result.statistics.total_distance_m > 0
    assert result.statistics.ascent_m is None
    assert result.statistics.observed_elapsed_s is None
    assert result.statistics.elevation_coverage == 0


def test_json_reproducible_and_source_keyed():
    """Report serialization is stable and retains canonical provenance."""
    source = dataset()
    first = analyze_route(source)
    second = analyze_route(source)
    assert route_analysis_json(first) == route_analysis_json(second)
    raw = json.loads(route_analysis_json(first))
    assert raw["source_sha256"] == source.source_sha256
    assert raw["schema_version"] == "1.0.0"


def test_reject_duplicate_or_foreign_segment_identity():
    """Reject segments not uniquely correlated with source point records."""
    source = dataset()
    broken = replace(source, segments=source.segments + (source.segments[0],))
    with pytest.raises(RouteAnalysisError, match="Duplicate segment"):
        analyze_route(broken)


def test_reject_incompatible_grade_threshold():
    """Grade-bin configuration requires a finite nonnegative threshold."""
    for threshold in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            RouteAnalysisOptions(flat_grade_percent=threshold)
