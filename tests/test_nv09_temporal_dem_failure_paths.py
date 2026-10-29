"""NV-09 defensive F04 chronology and F03 direct DEM sampling tests."""

from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx
from gpx_pipeline.dem import DEMError, enrich_dem
from gpx_pipeline.temporal import TemporalError, analyze_temporal


_NS = "http://www.topografix.com/GPX/1/1"


def _gpx(body):
    """Preserve source structure and allow intentionally invalid GPX coordinates."""
    return parse_gpx(
        (f'<gpx xmlns="{_NS}" version="1.1" creator="nv09">'
         f"{body}</gpx>").encode("utf-8"),
        strict=False,
    )


def _raster(tmp_path, *, count=1, crs="EPSG:4326"):
    """Write an explicit unit-bearing raster for direct F03 sampling."""
    path = tmp_path / "nv09.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=4, height=4, count=count,
        dtype="float32", crs=crs, nodata=-9999,
        transform=from_origin(0, 2, 0.5, 0.5),
    ) as raster:
        for band in range(1, count + 1):
            raster.write(np.full((4, 4), 50, dtype=np.float32), band)
            raster.set_band_unit(band, "m")
    return path


def test_temporal_rejects_spatial_invalidity_before_rate_calculation():
    """Malformed geometry cannot enter speed computations."""
    source = _gpx(
        '<trk><trkseg><trkpt lat="91" lon="0">'
        '<time>2026-01-01T00:00:00Z</time></trkpt>'
        '<trkpt lat="0" lon="1"><time>2026-01-01T00:01:00Z</time>'
        '</trkpt></trkseg></trk>'
    )
    with pytest.raises(TemporalError, match="F02 spatial validation failed"):
        analyze_temporal(source)


@pytest.mark.parametrize(
    ("distance_sequences", "message"),
    [
        ((), "F02 segment count mismatch"),
        (((),), "F02 distance array mismatch"),
        (((float("nan"),),), "F02 returned invalid geodesic distance"),
    ],
)
def test_temporal_rejects_corrupted_upstream_distance_contracts(
    monkeypatch, distance_sequences, message,
):
    """Inject an invalid upstream F02 result to test defensive boundaries."""
    import gpx_pipeline.temporal as temporal

    source = _gpx(
        '<trk><trkseg>'
        '<trkpt lat="0" lon="0"><time>2026-01-01T00:00:00Z</time></trkpt>'
        '<trkpt lat="0" lon="0.001"><time>2026-01-01T00:01:00Z</time>'
        '</trkpt></trkseg></trk>'
    )
    monkeypatch.setattr(
        temporal, "validate_spatial",
        lambda _source: SimpleNamespace(valid=True, distances_m=distance_sequences),
    )
    with pytest.raises(TemporalError, match=message):
        analyze_temporal(source)


def test_dem_direct_sampling_covers_route_point_identity(tmp_path):
    """GPX routes receive correctly scoped DEM samples without track coercion."""
    source = _gpx(
        '<rte><rtept lat="1.75" lon="0.25"/>'
        '<rtept lat="1.25" lon="0.75"/></rte>'
    )
    result = enrich_dem(source, _raster(tmp_path))
    assert [(s.kind, s.index, s.segment, s.point) for s in result.samples] == [
        ("route", 0, None, 0), ("route", 0, None, 1),
    ]
    assert all(s.elevation_m == 50 and s.status == "ok" for s in result.samples)


@pytest.mark.parametrize(
    ("count", "crs", "message"),
    [
        (2, "EPSG:4326", "single-band"),
        (1, None, "CRS must be defined"),
    ],
)
def test_dem_direct_sampling_rejects_invalid_raster_metadata(
    tmp_path, count, crs, message,
):
    """Unsupported raster metadata cannot be treated as known metric heights."""
    source = _gpx('<wpt lat="1.75" lon="0.25"/>')
    with pytest.raises(DEMError, match=message):
        enrich_dem(source, _raster(tmp_path, count=count, crs=crs))


def test_dem_direct_sampling_rejects_missing_or_corrupt_raster(tmp_path):
    """Absent and invalid GeoTIFF paths produce controlled DEMError."""
    source = _gpx('<wpt lat="1.75" lon="0.25"/>')
    with pytest.raises(DEMError, match="does not exist"):
        enrich_dem(source, tmp_path / "not-found.tif")
    invalid = tmp_path / "invalid.tif"
    invalid.write_bytes(b"not a valid raster")
    with pytest.raises(DEMError, match="DEM read failed"):
        enrich_dem(source, invalid)
