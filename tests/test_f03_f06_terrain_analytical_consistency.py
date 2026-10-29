"""F03/F06 raster, numerical-surface, and analytical integrity regressions.

Fixtures are synthetic and measurements are compared with independent formulas.
"""

from dataclasses import replace
from math import atan, degrees, hypot
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import DEMError, DEMOptions, enrich_dem
from gpx_pipeline.dem_sampling_adapter import sample_terrain_from_dem
from gpx_pipeline.route_analysis import RouteAnalysisError, analyze_route
from gpx_pipeline.terrain import TerrainError, analyze_dem_surface, analyze_terrain

NS = "http://www.topografix.com/GPX/1/1"


def source(*, elevation=False):
    """Two close vertices inside a geographic DEM and an immutable source."""
    height = "<ele>999</ele>" if elevation else ""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="reference">'
         '<trk><trkseg>'
         f'<trkpt lat="2.5" lon="0.5">{height}</trkpt>'
         '<trkpt lat="2.4999" lon="0.5001"/>'
         '</trkseg></trk></gpx>').encode(), strict=False,
    )


def raster(tmp_path, *, crs="EPSG:4326", units="m", bands=1, scale=1):
    """Generate a small local GeoTIFF with deliberately explicit metadata."""
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=5, height=5, count=bands,
        dtype="float32", crs=crs,
        transform=from_origin(0, 3, scale, scale), nodata=-9999,
    ) as dst:
        for band in range(1, bands + 1):
            dst.write(np.full((5, 5), 100, dtype="float32"), band)
            dst.set_band_unit(band, units)
    return path


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"uncertainty_m": -1}, "uncertainty_m"),
        ({"uncertainty_m": float("nan")}, "uncertainty_m"),
        ({"vertical_datum": ""}, "vertical_datum"),
        ({"vertical_datum": 4}, "vertical_datum"),
    ],
)
def test_adapter_rejects_invalid_metadata_before_read(tmp_path, kwargs, error):
    """No invalid lineage metadata enters the analytical result."""
    data = build_analytical_dataset(source(), include_temporal=False)
    with pytest.raises(ValueError, match=error):
        sample_terrain_from_dem(data, tmp_path / "unused.tif", **kwargs)


def test_adapter_missing_dem_is_explicit(tmp_path):
    """An absent raster is not silently treated as flat terrain."""
    data = build_analytical_dataset(source(), include_temporal=False)
    with pytest.raises(DEMError, match="does not exist"):
        sample_terrain_from_dem(data, tmp_path / "absent.tif")


def test_adapter_enforces_file_byte_limit(tmp_path):
    """Raster byte limits are checked before opening the dataset."""
    data = build_analytical_dataset(source(), include_temporal=False)
    path = raster(tmp_path)
    with pytest.raises(DEMError, match="byte limit"):
        sample_terrain_from_dem(
            data, path, dem_options=DEMOptions(max_raster_bytes=1),
        )


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"bands": 2}, "single-band"),
        ({"crs": None}, "CRS must be defined"),
        ({"units": "ft"}, "explicitly be metres"),
    ],
)
def test_adapter_rejects_unsupported_raster_metadata(
    tmp_path, options, expected,
):
    """Reject metadata that would invalidate inferred elevation units."""
    data = build_analytical_dataset(source(), include_temporal=False)
    path = raster(tmp_path, **options)
    with pytest.raises(DEMError, match=expected):
        sample_terrain_from_dem(data, path)


def test_adapter_rejects_scaled_raster_band(tmp_path):
    data = build_analytical_dataset(source(), include_temporal=False)
    path = raster(tmp_path)
    with rasterio.open(path, "r+") as dst:
        dst.scales = [2.0]
    with pytest.raises(DEMError, match="Scaled/offset"):
        sample_terrain_from_dem(data, path)


def test_adapter_sample_budget_exhaustion(tmp_path):
    """Sampling callbacks must not exceed their explicit operation budget."""
    data = build_analytical_dataset(source(), include_temporal=False)
    path = raster(tmp_path)
    with pytest.raises(DEMError, match="operation limit"):
        sample_terrain_from_dem(
            data, path, dem_options=DEMOptions(max_points=1),
        )


def projected_surface(tmp_path, values):
    """Create a 10-meter-resolution projected test surface."""
    path = tmp_path / "surface.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=5, height=5, count=1,
        dtype="float32", crs="EPSG:32616",
        transform=from_origin(500000, 1500000, 10, 10), nodata=-9999,
    ) as dst:
        dst.write(np.asarray(values, dtype="float32"), 1)
        dst.set_band_unit(1, "m")
    return path


def test_horn_slope_matches_independent_planar_gradient(tmp_path):
    """z=100+2*column+3*row has dz/dx=.2 and dz/dy=.3."""
    values = np.fromfunction(lambda row, col: 100 + 2*col + 3*row, (5, 5))
    result = analyze_dem_surface(projected_surface(tmp_path, values), 2, 2)
    expected_angle = degrees(atan(hypot(0.2, 0.3)))
    assert result.slope_degrees == pytest.approx(expected_angle, abs=1e-6)
    assert result.relief_m == pytest.approx(10.0)
    assert result.valid_cells == result.total_cells == 9


def test_outer_nodata_invalidates_relief_but_not_central_slope(tmp_path):
    """A larger 5x5 window can lack relief while its 3x3 core remains valid."""
    values = np.full((5, 5), 70.0)
    values[0, 0] = -9999
    result = analyze_dem_surface(
        projected_surface(tmp_path, values), 2, 2, window_cells=5,
    )
    assert result.relief_m is None
    assert result.slope_degrees == pytest.approx(0.0)
    assert (result.valid_cells, result.total_cells) == (24, 25)


def test_surface_requires_metric_projected_crs(tmp_path):
    """Geographic horizontal degrees must not be interpreted as metres."""
    with pytest.raises(TerrainError, match="Projected CRS"):
        analyze_dem_surface(raster(tmp_path), 2, 2)


def test_surface_rejects_missing_elevation_units(tmp_path):
    path = projected_surface(tmp_path, np.full((5, 5), 1.0))
    with rasterio.open(path, "r+") as dst:
        dst.set_band_unit(1, "ft")
    with pytest.raises(TerrainError, match="Metre elevation"):
        analyze_dem_surface(path, 2, 2)


def test_missing_dem_observation_stays_unknown_through_analysis(tmp_path):
    """NoData propagates without overwriting recorded GPX elevation text."""
    doc = source(elevation=True)
    original = doc.xml
    path = raster(tmp_path)
    with rasterio.open(path, "r+") as dst:
        values = dst.read(1)
        values[0, 0] = -9999
        dst.write(values, 1)
    dem = enrich_dem(doc, path)
    assert dem.samples[0].elevation_m is None
    terrain = analyze_terrain(doc, dem)
    assert terrain.segments[0].complete is False
    dataset = build_analytical_dataset(doc, dem=dem, include_temporal=False)
    analysis = analyze_route(dataset)
    assert dataset.points[0].recorded_elevation_text == "999"
    assert dataset.points[0].dem_elevation_m is None
    assert analysis.statistics.ascent_m is None
    assert "PARTIAL_OR_UNAVAILABLE_TERRAIN" in analysis.diagnostics
    assert doc.xml == original


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": "2.0.0"}, "Unsupported analytical dataset schema"),
    ],
)
def test_route_rejects_unknown_dataset_contract(change, message):
    data = build_analytical_dataset(source(), include_temporal=False)
    with pytest.raises(RouteAnalysisError, match=message):
        analyze_route(replace(data, **change))


def test_route_rejects_foreign_point_segment_identity():
    """A stray analytical point cannot be assigned to an unknown segment."""
    data = build_analytical_dataset(source(), include_temporal=False)
    foreign = replace(data.points[0], index=9)
    with pytest.raises(RouteAnalysisError, match="unknown segments"):
        analyze_route(replace(data, points=data.points + (foreign,)))


def test_route_rejects_mismatched_point_count():
    """Segment declarations must match actual analytical point records."""
    data = build_analytical_dataset(source(), include_temporal=False)
    segment = replace(data.segments[0], point_count=3)
    with pytest.raises(RouteAnalysisError, match="point count mismatch"):
        analyze_route(replace(data, segments=(segment,)))


def test_route_rejects_nonfinite_derived_grade():
    """NaN grades cannot masquerade as valid analytical observations."""
    data = build_analytical_dataset(source(), include_temporal=False)
    bad = replace(data.points[1], grade_percent=float("nan"))
    segment = replace(data.segments[0], terrain_complete=True)
    with pytest.raises(RouteAnalysisError, match="Non-finite grade"):
        analyze_route(replace(data, points=(data.points[0], bad),
                              segments=(segment,)))
