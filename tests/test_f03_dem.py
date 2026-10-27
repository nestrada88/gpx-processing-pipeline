"""Synthetic-raster DEM sampling and source-preservation tests."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.dem import DEMError, DEMOptions, enrich_dem

NS = "http://www.topografix.com/GPX/1/1"


def gpx(points: str):
    """Create source with direct coordinate and elevation observations."""
    source = (
        f'<gpx xmlns="{NS}" version="1.1" creator="test">'
        f'<trk><trkseg>{points}</trkseg></trk></gpx>'
    ).encode()
    return parse_gpx(source, strict=False)


def raster(tmp_path: Path, *, units: str = "m", nodata: float = -9999):
    """Generate an explicitly georeferenced three-by-three DEM."""
    path = tmp_path / "synthetic.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=3, width=3, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(0, 3, 1, 1), nodata=nodata,
    ) as dataset:
        dataset.write(np.array(
            [[10, 20, 30], [40, 50, 60], [70, 80, 90]],
            dtype="float32",
        ), 1)
        dataset.set_band_unit(1, units)
    return path


def test_nearest_center_and_observation_preservation(tmp_path):
    """Derive elevation without modifying recorded GPX elevation."""
    source = gpx(
        '<trkpt lat="2.5" lon="0.5"><ele>999</ele></trkpt>'
    )
    before = serialize_gpx(source)
    result = enrich_dem(source, raster(tmp_path), vertical_datum="test-grid")
    assert result.samples[0].elevation_m == 10
    assert result.samples[0].status == "ok"
    assert result.provenance.vertical_datum == "test-grid"
    assert serialize_gpx(source) == before


def test_bilinear_cell_centers(tmp_path):
    """Bilinear interpolation averages four centers at their midpoint."""
    source = gpx('<trkpt lat="2" lon="1"/>')
    result = enrich_dem(
        source, raster(tmp_path),
        options=DEMOptions(method="bilinear"),
    )
    assert result.samples[0].elevation_m == pytest.approx(30)


def test_missing_coverage_and_nodata(tmp_path):
    """A raster miss must be explicit, not fabricated as zero."""
    path = raster(tmp_path)
    source = gpx(
        '<trkpt lat="2.5" lon="0.5"/>'
        '<trkpt lat="-10" lon="-10"/>'
    )
    with rasterio.open(path, "r+") as dataset:
        block = dataset.read(1)
        block[0, 0] = -9999
        dataset.write(block, 1)
    result = enrich_dem(source, path)
    assert [s.status for s in result.samples] == ["missing", "missing"]
    assert all(s.elevation_m is None for s in result.samples)


def test_bilinear_rejects_nodata_neighbor(tmp_path):
    """Interpolation never fills missing neighbors by renormalization."""
    path = raster(tmp_path)
    with rasterio.open(path, "r+") as dataset:
        data = dataset.read(1)
        data[1, 1] = -9999
        dataset.write(data, 1)
    result = enrich_dem(
        gpx('<trkpt lat="2" lon="1"/>'),
        path, options=DEMOptions(method="bilinear"),
    )
    assert result.samples[0].status == "missing"


def test_invalid_spatial_data_rejected(tmp_path):
    """F02 invalid coordinate findings block DEM processing."""
    with pytest.raises(DEMError, match="F02"):
        enrich_dem(gpx('<trkpt lat="91" lon="0"/>'), raster(tmp_path))


def test_unsupported_units_fail_closed(tmp_path):
    """Unknown DEM vertical units cannot be treated as metres."""
    with pytest.raises(DEMError, match="units"):
        enrich_dem(gpx('<trkpt lat="2.5" lon="0.5"/>'),
                   raster(tmp_path, units="ft"))


def test_resource_limit(tmp_path):
    """Respect configured raster bytes and sample count."""
    source = gpx('<trkpt lat="2.5" lon="0.5"/>')
    path = raster(tmp_path)
    with pytest.raises(DEMError, match="byte limit"):
        enrich_dem(source, path, options=DEMOptions(max_raster_bytes=1))
    two_points = gpx('<trkpt lat="2.5" lon="0.5"/>'
                     '<trkpt lat="1.5" lon="0.5"/>')
    with pytest.raises(DEMError, match="sample count"):
        enrich_dem(two_points, path, options=DEMOptions(max_points=1))
