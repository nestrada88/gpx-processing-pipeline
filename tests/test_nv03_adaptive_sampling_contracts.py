"""NV-03 adaptive sampling boundary and source-preservation contracts."""

from math import isclose

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.terrain_sampling import (
    SamplingOptions, terrain_adaptive_sample,
)


_NS = "http://www.topografix.com/GPX/1/1"


def _dataset():
    xml = (
        f'<gpx xmlns="{_NS}" version="1.1" creator="nv03">'
        '<trk><trkseg><trkpt lat="0" lon="0"/>'
        '<trkpt lat="0" lon="0.02"/></trkseg></trk></gpx>'
    ).encode("utf-8")
    document = parse_gpx(xml, strict=False)
    return document, build_analytical_dataset(document, include_temporal=False)


def test_spacing_and_source_lineage_when_budget_allows():
    """Flat elevation yields bounded geodesic spacing and intact endpoints."""
    source, dataset = _dataset()
    before = serialize_gpx(source)
    result = terrain_adaptive_sample(
        dataset, lambda lat, lon: 50,
        dem_source_description="synthetic-flat",
        options=SamplingOptions(
            max_spacing_m=200, min_spacing_m=1, max_depth=12,
        ),
    )
    segment = result.segments[0]
    points = segment.points
    assert len(points) > 2
    assert points[0].source_point_index == 0
    assert points[-1].source_point_index == 1
    assert all(p.geometry_origin == "geodesic_interpolation"
               for p in points[1:-1])
    distances = [
        b.distance_from_segment_start_m - a.distance_from_segment_start_m
        for a, b in zip(points, points[1:])
    ]
    assert all(0 < distance <= 200.001 for distance in distances)
    assert isclose(
        segment.horizontal_distance_m,
        dataset.segments[0].horizontal_distance_m,
        abs_tol=.01,
    )
    assert "SAMPLING_RESOLUTION_LIMIT" not in result.diagnostics
    assert serialize_gpx(source) == before


def test_insufficient_refinement_depth_is_explicitly_diagnosed():
    """A requested resolution that cannot be achieved is not claimed as met."""
    _, dataset = _dataset()
    result = terrain_adaptive_sample(
        dataset, lambda lat, lon: 50,
        dem_source_description="synthetic-flat",
        options=SamplingOptions(
            max_spacing_m=10, min_spacing_m=1, max_depth=1,
        ),
    )
    assert "SAMPLING_RESOLUTION_LIMIT" in result.diagnostics
    assert len(result.segments[0].points) == 3
    assert result.segments[0].points[0].source_point_index == 0
    assert result.segments[0].points[-1].source_point_index == 1
