"""NV-02 DEM interpolation, projected-CRS and datum declaration contracts."""

from math import isclose

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import DEMOptions, enrich_dem
from gpx_pipeline.dem_sampling_adapter import sample_terrain_from_dem


_NS = "http://www.topografix.com/GPX/1/1"


def _source(latitude: float, longitude: float):
    """Build a lossless GPX source with an observed elevation distinct from DEM."""
    xml = (
        f'<gpx xmlns="{_NS}" version="1.1" creator="nv02">'
        f'<trk><trkseg><trkpt lat="{latitude}" lon="{longitude}">'
        "<ele>999</ele></trkpt></trkseg></trk></gpx>"
    ).encode()
    return parse_gpx(xml, strict=False)


def _dem(tmp_path, *, crs="EPSG:4326", values=None, nodata=-9999):
    """Write a metric-height synthetic raster with known center positions."""
    if values is None:
        values = np.array([[10, 20], [30, 40]], dtype=np.float32)
    path = tmp_path / "nv02.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=2, height=2, count=1,
        dtype="float32", crs=crs, nodata=nodata,
        transform=(
            from_origin(0, 2, 1, 1)
            if crs == "EPSG:4326"
            else from_origin(0, 2000, 1000, 1000)
        ),
    ) as raster:
        raster.write(values, 1)
        raster.set_band_unit(1, "m")
    return path


def test_fractional_bilinear_plane_has_fixed_reference(tmp_path):
    """Weighted result is independently calculated from four pixel heights."""
    source = _source(1.25, 0.75)
    unchanged = serialize_gpx(source)
    result = enrich_dem(
        source, _dem(tmp_path), options=DEMOptions(method="bilinear"),
        vertical_datum="synthetic-metric-height",
    )
    # Pixel fractional coordinates: u=0.25 and v=0.25.
    expected = 10 * .75 * .75 + 20 * .25 * .75 + 30 * .75 * .25 + 40 * .25 * .25
    assert isclose(result.samples[0].elevation_m, expected, abs_tol=1e-6)
    assert result.samples[0].status == "ok"
    assert serialize_gpx(source) == unchanged
    assert result.provenance.vertical_datum == "synthetic-metric-height"


def test_projected_crs_samples_expected_metric_pixel(tmp_path):
    """Projection transforms WGS84 longitude/latitude into raster metres."""
    path = _dem(tmp_path, crs="EPSG:3857")
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    longitude, latitude = transformer.transform(1500, 1500)
    result = enrich_dem(_source(latitude, longitude), path)
    assert result.samples[0].status == "ok"
    assert result.samples[0].elevation_m == 20
    assert result.provenance.horizontal_crs == "EPSG:3857"


@pytest.mark.parametrize("declared", ["", " ", "\t", "\n"])
def test_invalid_vertical_datum_declarations_rejected_consistently(tmp_path, declared):
    """Both F03 entrypoints reject unusable non-None vertical datum metadata."""
    source = _source(1.5, 0.5)
    raster_path = _dem(tmp_path)
    with pytest.raises(ValueError, match="vertical_datum"):
        enrich_dem(source, raster_path, vertical_datum=declared)
    dataset = build_analytical_dataset(source, include_temporal=False)
    with pytest.raises(ValueError, match="vertical_datum"):
        sample_terrain_from_dem(dataset, raster_path, vertical_datum=declared)


def test_unknown_vertical_reference_is_explicit_not_assumed(tmp_path):
    """Unknown datum remains None; recorded elevations are never overwritten."""
    source = _source(1.5, 0.5)
    original = serialize_gpx(source)
    result = enrich_dem(source, _dem(tmp_path))
    assert result.provenance.vertical_datum is None
    assert result.samples[0].elevation_m == 10
    dataset = build_analytical_dataset(source, dem=result, include_temporal=False)
    assert dataset.points[0].recorded_elevation_text == "999"
    assert dataset.points[0].dem_elevation_m == 10
    assert dataset.dem_vertical_datum is None
    assert serialize_gpx(source) == original
