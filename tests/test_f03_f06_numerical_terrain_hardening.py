"""Independent numerical references and fail-closed F03/F06 regressions."""

from dataclasses import replace
from math import nan

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx
from gpx_pipeline.dem import DEMError, DEMOptions, enrich_dem
from gpx_pipeline.route_analysis import (
    RouteAnalysisError, _edge_lengths, _grade_distribution, analyze_route,
)
from gpx_pipeline.analytical import build_analytical_dataset

NS = "http://www.topografix.com/GPX/1/1"


def _source(points):
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="numerical">'
         '<trk><trkseg>' + points + '</trkseg></trk></gpx>').encode(),
        strict=False,
    )


def _raster(tmp_path, values, *, scale=1.0, offset=0.0):
    path = tmp_path / "grid.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=3, width=3,
        count=1, dtype="float32", crs="EPSG:4326",
        transform=from_origin(0, 3, 1, 1), nodata=-9999,
    ) as ds:
        ds.write(np.asarray(values, dtype="float32"), 1)
        ds.set_band_unit(1, "m")
        ds.scales = [scale]
        ds.offsets = [offset]
    return path


@pytest.mark.parametrize("method", ["cubic", "", "NEAREST"])
def test_f03_rejects_unsupported_interpolation(method):
    with pytest.raises(ValueError, match="nearest or bilinear"):
        DEMOptions(method=method)


@pytest.mark.parametrize("kwargs", [
    {"max_points": 0}, {"max_points": -1},
    {"max_raster_bytes": 0}, {"max_raster_bytes": -1},
])
def test_f03_rejects_nonpositive_sampling_budgets(kwargs):
    with pytest.raises(ValueError, match="Resource limits"):
        DEMOptions(**kwargs)


@pytest.mark.parametrize("uncertainty", [-0.001, nan, float("inf")])
def test_f03_rejects_invalid_uncertainty(tmp_path, uncertainty):
    doc = _source('<trkpt lat="2.5" lon="0.5"/>')
    with pytest.raises(ValueError, match="uncertainty_m"):
        enrich_dem(doc, tmp_path / "unused.tif", uncertainty_m=uncertainty)


def test_f03_bilinear_weighted_plane_has_independent_reference(tmp_path):
    """For z=10+20*col+30*row, continuous interpolation is affine."""
    values = [[10 + 20*c + 30*r for c in range(3)] for r in range(3)]
    path = _raster(tmp_path, values)
    # Raster cell centers: (lon=.5,lat=2.5) is (row=0,col=0).
    # (lon=1.25,lat=1.75) corresponds to (row=0.75,col=0.75).
    doc = _source(
        '<trkpt lat="2.5" lon="0.5"><ele>999</ele></trkpt>'
        '<trkpt lat="1.75" lon="1.25"/>'
    )
    before = doc.xml
    result = enrich_dem(doc, path, options=DEMOptions(method="bilinear"))
    assert [s.status for s in result.samples] == ["ok", "ok"]
    assert [s.elevation_m for s in result.samples] == pytest.approx(
        [10, 10 + 20*.75 + 30*.75],
        abs=1e-10,
    )
    assert doc.xml == before


@pytest.mark.parametrize("scale,offset", [(2.0, 0.0), (1.0, 10.0)])
def test_f03_rejects_scaled_or_offset_elevation_bands(tmp_path, scale, offset):
    path = _raster(tmp_path, [[10]*3]*3, scale=scale, offset=offset)
    with pytest.raises(DEMError, match="Scaled/offset"):
        enrich_dem(_source('<trkpt lat="2.5" lon="0.5"/>'), path)


@pytest.mark.parametrize(
    "distances,total,error",
    [
        ([0.0, -1.0], 0.0, "Invalid cumulative"),
        ([1.0, 2.0], 2.0, "begin at zero"),
        ([0.0, 2.0], 3.0, "do not match"),
        ([0.0, nan], 0.0, "Invalid cumulative"),
    ],
)
def test_f06_rejects_invalid_distance_invariants(distances, total, error):
    """Distance accounting is checked independently of spatial I/O."""
    points = [type("P", (), {"cumulative_distance_m": value})()
              for value in distances]
    with pytest.raises(RouteAnalysisError, match=error):
        _edge_lengths(points, total)


def test_f06_reference_grade_bins_weight_by_distance_not_point_count():
    """The explicit reference is 30m uphill, 10m downhill, 60m flat."""
    grades = [None, 2.0, -3.0, 0.5, None]
    points = [type("P", (), {"grade_percent": grade})() for grade in grades]
    out = _grade_distribution(points, [30.0, 10.0, 60.0, 7.0], 1.0)
    assert (out.uphill_edges, out.downhill_edges,
            out.flat_edges, out.undefined_edges) == (1, 1, 1, 1)
    assert (out.uphill_distance_m, out.downhill_distance_m,
            out.flat_distance_m) == pytest.approx((30.0, 10.0, 60.0))
    assert out.valid_distance_m == pytest.approx(100.0)


def test_f06_grade_on_zero_distance_is_not_finite_slope():
    points = [type("P", (), {"grade_percent": x})() for x in (None, 5.0)]
    with pytest.raises(RouteAnalysisError, match="zero-distance"):
        _grade_distribution(points, [0.0], 1.0)


def test_f06_unknown_terrain_never_becomes_zero_ascent():
    doc = _source(
        '<trkpt lat="12" lon="-86"/>'
        '<trkpt lat="12.001" lon="-86.001"/>'
    )
    result = analyze_route(build_analytical_dataset(doc, include_temporal=False))
    assert result.statistics.ascent_m is None
    assert result.statistics.descent_m is None
    assert result.statistics.elevation_coverage == 0
    assert "PARTIAL_OR_UNAVAILABLE_TERRAIN" in result.diagnostics
