"""Regression tests for bounded terrain-adaptive analytical sampling."""

from math import isclose
import json

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.terrain_sampling import (
    SamplingError, SamplingOptions, terrain_adaptive_sample,
    terrain_sampling_json,
)

NS = "http://www.topografix.com/GPX/1/1"


def fixture(*segments):
    """Create independent source segments of sparse original vertices."""
    body = "".join(
        "<trkseg>" + "".join(
            f'<trkpt lat="{lat}" lon="{lon}"/>'
            for lat, lon in points
        ) + "</trkseg>"
        for points in segments
    )
    xml = (f'<gpx xmlns="{NS}" version="1.1" creator="test">'
           f"<trk>{body}</trk></gpx>").encode()
    source = parse_gpx(xml, strict=False)
    return source, build_analytical_dataset(
        source, include_temporal=False
    )


def test_flat_dem_spatial_densification_preserves_source():
    """Bound spacing, reuse original endpoints and preserve GPX snapshot."""
    source, data = fixture([(0, 0), (0, .01)])
    before = serialize_gpx(source)
    result = terrain_adaptive_sample(
        data, lambda lat, lon: 100.,
        dem_source_description="synthetic-flat",
        options=SamplingOptions(max_spacing_m=250, min_spacing_m=1),
    )
    points = result.segments[0].points
    assert len(points) > 2
    assert points[0].source_point_index == 0
    assert points[-1].source_point_index == 1
    assert all(p.dem_elevation_m == 100 for p in points)
    assert all(p.grade_from_previous_percent in (None, 0.) for p in points)
    assert all(
        b.distance_from_segment_start_m - a.distance_from_segment_start_m
        <= 250.01 for a, b in zip(points, points[1:])
    )
    assert result.segments[0].horizontal_distance_m == pytest.approx(
        data.segments[0].horizontal_distance_m, abs=.05
    )
    assert serialize_gpx(source) == before


def test_dem_curvature_refines_short_edge():
    """A nonlinear elevation surface drives refinement beyond length limits."""
    _, data = fixture([(0, 0), (0, .002)])
    def terrain(lat, lon):
        return 100. + 20. * (1 - ((lon - .001) / .001) ** 2)
    result = terrain_adaptive_sample(
        data, terrain, dem_source_description="curved-dem",
        options=SamplingOptions(
            max_spacing_m=1000, elevation_residual_m=1,
            min_spacing_m=1,
        ),
    )
    assert len(result.segments[0].points) > 2
    assert any(p.geometry_origin == "geodesic_interpolation"
               for p in result.segments[0].points)


def test_missing_dem_does_not_invent_flat_grade():
    """Geometric spacing remains while elevation and grade are nullable."""
    _, data = fixture([(0, 0), (0, .01)])
    result = terrain_adaptive_sample(
        data, lambda lat, lon: None,
        dem_source_description="nodata",
        options=SamplingOptions(max_spacing_m=250, min_spacing_m=1),
    )
    assert result.segments[0].points
    assert not result.segments[0].complete
    assert all(p.grade_from_previous_percent is None
               for p in result.segments[0].points)
    assert "DEM_COVERAGE_INCOMPLETE" in result.diagnostics


def test_independent_segments_do_not_join():
    """Do not interpolate across discontinuities in source segments."""
    _, data = fixture(
        [(0, 0), (0, .001)],
        [(10, 10), (10, 10.001)],
    )
    result = terrain_adaptive_sample(
        data, lambda lat, lon: 0,
        dem_source_description="flat",
    )
    assert len(result.segments) == 2
    assert len(result.segments[0].points) == 2
    assert len(result.segments[1].points) == 2
    assert result.segments[1].points[0].distance_from_segment_start_m == 0


def test_resources_fail_closed_and_report_resolution():
    """Large output and insufficient subdivision depth are distinguishable."""
    _, data = fixture([(0, 0), (0, .02)])
    with pytest.raises(SamplingError, match="max_output_points"):
        terrain_adaptive_sample(
            data, lambda lat, lon: 5.,
            dem_source_description="flat",
            options=SamplingOptions(
                max_spacing_m=10, min_spacing_m=1, max_output_points=2,
            ),
        )
    partial = terrain_adaptive_sample(
        data, lambda lat, lon: 5.,
        dem_source_description="flat",
        options=SamplingOptions(
            max_spacing_m=10, min_spacing_m=1, max_depth=1,
        ),
    )
    assert "SAMPLING_RESOLUTION_LIMIT" in partial.diagnostics


def test_deterministic_json_and_provenance():
    """Repeat calls yield identical JSON with canonical source identity."""
    _, data = fixture([(0, 0), (0, .001)])
    first = terrain_adaptive_sample(
        data, lambda lat, lon: 33., dem_source_description="reference-dem"
    )
    second = terrain_adaptive_sample(
        data, lambda lat, lon: 33., dem_source_description="reference-dem"
    )
    assert terrain_sampling_json(first) == terrain_sampling_json(second)
    report = json.loads(terrain_sampling_json(first))
    assert report["source_sha256"] == data.source_sha256
    assert report["dem_source_description"] == "reference-dem"


@pytest.mark.parametrize("option", [
    {"max_spacing_m": 0}, {"elevation_residual_m": float("nan")},
    {"min_spacing_m": -1}, {"max_depth": True},
    {"max_output_points": 0}, {"min_spacing_m": 300, "max_spacing_m": 100},
])
def test_reject_invalid_options(option):
    """Enforce finite physical and bounded computational limits."""
    with pytest.raises(ValueError):
        SamplingOptions(**option)


def test_invalid_dem_value_is_rejected():
    """Never serialize NaN/Infinity as a valid terrain elevation."""
    _, data = fixture([(0, 0), (0, .001)])
    with pytest.raises(SamplingError):
        terrain_adaptive_sample(
            data, lambda lat, lon: float("nan"),
            dem_source_description="broken-dem",
        )
