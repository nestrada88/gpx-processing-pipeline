"""F03 terrain-analytics numerical and integration tests."""

from dataclasses import replace
from math import atan, degrees

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.spatial import geodesic_distance_m
from gpx_pipeline.terrain import (
    TerrainError, analyze_dem_surface, analyze_terrain,
)

NS = "http://www.topografix.com/GPX/1/1"


def fixture(heights, *, segments=1):
    """Generate source geometry and keyed DEM elevations."""
    parts = []
    samples = []
    for segment in range(segments):
        points = []
        for index, height in enumerate(heights):
            points.append(
                f'<trkpt lat="0" lon="{index * 0.001}">'
                f'<ele>9999</ele></trkpt>'
            )
            samples.append(
                DEMSample("track", 0, segment, index, height,
                          "ok" if height is not None else "missing")
            )
        parts.append("<trkseg>" + "".join(points) + "</trkseg>")
    data = (f'<gpx xmlns="{NS}" version="1.1" creator="test">'
            f'<trk>{"".join(parts)}</trk></gpx>').encode()
    provenance = DEMProvenance(
        "synthetic", "EPSG:4326", "test-datum", "m", (1, 1),
        "nearest", None,
    )
    return parse_gpx(data, strict=False), DEMResult(
        tuple(samples), provenance
    )


def test_flat_and_uphill_grade():
    """Flat profiles have no gain; uphill profile has correct grade."""
    flat_doc, flat_dem = fixture([100, 100, 100])
    flat = analyze_terrain(flat_doc, flat_dem).segments[0]
    assert flat.ascent_m == flat.descent_m == 0
    assert flat.points[1].grade_percent == 0
    doc, dem = fixture([100, 110, 120])
    before = serialize_gpx(doc)
    segment = analyze_terrain(doc, dem).segments[0]
    horizontal = geodesic_distance_m(0, 0, 0, 0.001)
    assert segment.ascent_m == 20
    assert segment.descent_m == 0
    assert segment.points[1].grade_percent == pytest.approx(1000/horizontal)
    assert segment.horizontal_distance_m == pytest.approx(2*horizontal)
    assert serialize_gpx(doc) == before


def test_downhill_and_oscillating():
    """Raw ascent/descent preserve all valid alternating changes."""
    doc, dem = fixture([100, 80, 90, 70])
    result = analyze_terrain(doc, dem).segments[0]
    assert result.ascent_m == 10
    assert result.descent_m == 40
    assert result.minimum_m == 70
    assert result.maximum_m == 100
    assert result.mean_m == 85


def test_missing_height_does_not_bridge():
    """A missing middle sample invalidates both adjacent gain edges."""
    doc, dem = fixture([100, None, 110])
    segment = analyze_terrain(doc, dem).segments[0]
    assert segment.ascent_m == 0
    assert segment.descent_m == 0
    assert not segment.complete
    assert segment.coverage_fraction == pytest.approx(2/3)
    assert segment.points[2].grade_percent is None


def test_segments_are_separate():
    """Identical segments do not form cross-segment distance edges."""
    doc, dem = fixture([100, 110], segments=2)
    result = analyze_terrain(doc, dem)
    assert len(result.segments) == 2
    assert [s.ascent_m for s in result.segments] == [10, 10]


def test_duplicate_dem_identifiers_rejected():
    """Reject ambiguous DEM point mapping."""
    doc, dem = fixture([100, 110])
    duplicate = replace(dem, samples=dem.samples + (dem.samples[0],))
    with pytest.raises(TerrainError, match="Duplicate"):
        analyze_terrain(doc, duplicate)


def test_missing_identifiers_rejected():
    """Do not silently align samples by sequence position."""
    doc, dem = fixture([100, 110])
    with pytest.raises(TerrainError, match="identities"):
        analyze_terrain(doc, replace(dem, samples=dem.samples[:1]))


def _surface(tmp_path, data):
    """Create metric projected DEM with explicit meter band units."""
    path = tmp_path / "surface.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=5, height=5,
        count=1, dtype="float32", crs="EPSG:32616",
        transform=from_origin(500000, 1500000, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(data.astype("float32"), 1)
        dst.set_band_unit(1, "m")
    return path


def test_planar_dem_slope_and_relief(tmp_path):
    """A 10 m-per-cell eastward rise yields unit horizontal gradient."""
    data = np.tile(np.arange(5, dtype=float) * 10, (5, 1))
    result = analyze_dem_surface(_surface(tmp_path, data), 2, 2)
    assert result.slope_degrees == pytest.approx(45, abs=1e-5)
    assert result.relief_m == pytest.approx(20)


def test_constant_surface(tmp_path):
    """Constant surface has zero inclination and zero relief."""
    data = np.full((5, 5), 120.)
    result = analyze_dem_surface(_surface(tmp_path, data), 2, 2)
    assert result.slope_degrees == 0
    assert result.relief_m == 0


def test_nodata_neighborhood(tmp_path):
    """A masked center makes relief and slope undefined."""
    data = np.full((5, 5), 120.)
    data[2, 2] = -9999
    result = analyze_dem_surface(_surface(tmp_path, data), 2, 2)
    assert result.slope_degrees is None
    assert result.relief_m is None
    assert result.valid_cells == 8


def test_surface_window_invalid(tmp_path):
    """Refuse out-of-bounds and even-sized analysis windows."""
    data = np.zeros((5, 5))
    path = _surface(tmp_path, data)
    with pytest.raises(TerrainError):
        analyze_dem_surface(path, 0, 0)
    with pytest.raises(ValueError):
        analyze_dem_surface(path, 2, 2, window_cells=4)
