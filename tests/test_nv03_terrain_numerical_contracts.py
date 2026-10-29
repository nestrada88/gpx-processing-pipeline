"""NV-03 terrain numerical contracts using independent synthetic references.

Raw ascent/descent, Horn plane derivatives and missing DEM coverage are
verified without using production terrain calculations as expected-value oracles.
"""

from math import atan, degrees, hypot, isclose

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.terrain import analyze_dem_surface, analyze_terrain


_NS = "http://www.topografix.com/GPX/1/1"


def _source(point_count=4):
    """Construct a single segment with distinct horizontal source vertices."""
    points = "".join(
        f'<trkpt lat="0" lon="{i / 1000}"/>'
        for i in range(point_count)
    )
    xml = (
        f'<gpx xmlns="{_NS}" version="1.1" creator="nv03">'
        f"<trk><trkseg>{points}</trkseg></trk></gpx>"
    ).encode("utf-8")
    return parse_gpx(xml, strict=False)


def _heights(values):
    """Construct position-identified synthetic DEM samples."""
    samples = tuple(
        DEMSample("track", 0, 0, i, value,
                  "ok" if value is not None else "missing")
        for i, value in enumerate(values)
    )
    provenance = DEMProvenance(
        source="synthetic-nv03", horizontal_crs="EPSG:4326",
        vertical_datum="synthetic", vertical_units="m",
        resolution=(1.0, 1.0), method="nearest", uncertainty_m=None,
    )
    return DEMResult(samples, provenance)


def _metric_raster(tmp_path, values):
    """Create a north-up 100 m metric raster with explicit vertical units."""
    path = tmp_path / "plane.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=5, width=5, count=1,
        dtype="float64", crs="EPSG:3857",
        transform=from_origin(0, 500, 100, 100), nodata=-9999,
    ) as raster:
        raster.write(values.astype("float64"), 1)
        raster.set_band_unit(1, "m")
    return path


def test_raw_ascent_descent_against_fixed_heights():
    """Raw positive/negative elevation increments use no implicit smoothing."""
    document = _source()
    before = serialize_gpx(document)
    segment = analyze_terrain(document, _heights((100, 103, 101, 105))).segments[0]
    assert segment.complete
    assert segment.ascent_m == 7
    assert segment.descent_m == 2
    assert (segment.minimum_m, segment.maximum_m, segment.mean_m) == (
        100, 105, 102.25,
    )
    assert all(p.grade_percent is not None for p in segment.points[1:])
    assert serialize_gpx(document) == before


def test_uniform_vertical_offset_preserves_relative_terrain_metrics():
    """A constant height shift cannot change grade or raw ascent/descent."""
    document = _source()
    first = analyze_terrain(document, _heights((100, 103, 101, 105))).segments[0]
    second = analyze_terrain(document, _heights((600, 603, 601, 605))).segments[0]
    assert first.ascent_m == second.ascent_m
    assert first.descent_m == second.descent_m
    assert first.horizontal_distance_m == second.horizontal_distance_m
    assert [p.grade_percent for p in first.points] == [
        p.grade_percent for p in second.points
    ]


def test_missing_sample_does_not_bridge_elevation_gap():
    """NoData makes adjacent edges unknown rather than inventing a slope."""
    segment = analyze_terrain(
        _source(), _heights((100, None, 110, 115))
    ).segments[0]
    assert not segment.complete
    assert segment.coverage_fraction == pytest.approx(.75)
    assert segment.ascent_m == 5
    assert segment.descent_m == 0
    assert segment.points[1].grade_percent is None
    assert segment.points[2].grade_percent is None
    assert segment.points[3].grade_percent is not None


def test_horn_slope_linear_plane_matches_analytic_gradient(tmp_path):
    """A planar 10 m/column and 20 m/row surface has exact Horn gradient."""
    row, col = np.indices((5, 5))
    values = 100.0 + 20.0 * row + 10.0 * col
    path = _metric_raster(tmp_path, values)
    metrics = analyze_dem_surface(path, 2, 2, window_cells=3)
    expected_angle = degrees(atan(hypot(10.0 / 100.0, 20.0 / 100.0)))
    assert isclose(metrics.slope_degrees, expected_angle, abs_tol=1e-10)
    assert isclose(metrics.relief_m, 60.0, abs_tol=1e-10)
    assert metrics.valid_cells == metrics.total_cells == 9
    extended = analyze_dem_surface(path, 2, 2, window_cells=5)
    assert isclose(extended.slope_degrees, expected_angle, abs_tol=1e-10)
    assert extended.relief_m == 120.0


def test_flat_surface_and_masked_cell_handling(tmp_path):
    """Flat terrain has zero slope; missing center makes slope unavailable."""
    path = _metric_raster(tmp_path, np.full((5, 5), 135.0))
    flat = analyze_dem_surface(path, 2, 2)
    assert flat.slope_degrees == 0
    assert flat.relief_m == 0
    with rasterio.open(path, "r+") as raster:
        data = raster.read(1)
        data[2, 2] = -9999
        raster.write(data, 1)
    incomplete = analyze_dem_surface(path, 2, 2)
    assert incomplete.slope_degrees is None
    assert incomplete.relief_m is None
    assert incomplete.valid_cells == 8
    assert incomplete.total_cells == 9


def test_raw_ascent_is_sensitive_to_alternating_height_noise():
    """Raw ascent responds to jitter; this test does not claim a noise filter."""
    document = _source(5)
    flat = analyze_terrain(document, _heights((100, 100, 100, 100, 100)))
    noisy = analyze_terrain(document, _heights((100, 101, 99, 101, 100)))
    a, b = flat.segments[0], noisy.segments[0]
    assert a.ascent_m == a.descent_m == 0
    assert b.ascent_m == 3
    assert b.descent_m == 3
    assert a.horizontal_distance_m == b.horizontal_distance_m
