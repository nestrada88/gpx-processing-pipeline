"""Synthetic-raster integration tests for the DEM sampling adapter."""

import json

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import DEMError, DEMOptions
from gpx_pipeline.dem_sampling_adapter import (
    dem_sampling_json,
    sample_terrain_from_dem,
)
from gpx_pipeline.terrain_sampling import SamplingOptions

_NS = "http://www.topografix.com/GPX/1/1"


def source(points):
    """Construct independent GPX geometry and analytical dataset."""
    segments = "".join(
        "<trkseg>" + "".join(
            f'<trkpt lat="{lat}" lon="{lon}"/>'
            for lat, lon in segment
        ) + "</trkseg>"
        for segment in points
    )
    xml = (
        f'<gpx xmlns="{_NS}" creator="test" version="1.1">'
        f"<trk>{segments}</trk></gpx>"
    ).encode()
    document = parse_gpx(xml, strict=False)
    return document, build_analytical_dataset(
        document, include_temporal=False
    )


def make_dem(tmp_path, *, crs="EPSG:4326", units="m",
             nodata=-9999, values=None):
    """Write an explicit single-band synthetic raster with metre units."""
    path = tmp_path / "terrain.tif"
    if values is None:
        values = np.full((16, 16), 100, dtype="float32")
    if crs == "EPSG:4326":
        transform = from_origin(0, 1, 0.001, 0.001)
    else:
        transform = from_origin(0, 1200, 100, 100)
    with rasterio.open(
        path, "w", driver="GTiff", height=16, width=16,
        count=1, dtype="float32", crs=crs,
        transform=transform, nodata=nodata,
    ) as raster:
        raster.write(values.astype("float32"), 1)
        raster.set_band_unit(1, units)
    return path


def test_flat_geographic_dem_preserves_source_and_lineage(tmp_path):
    """Sample local raster with no mutation of source coordinates."""
    document, data = source([[(0.995, 0.001), (0.995, 0.012)]])
    path = make_dem(tmp_path)
    original = serialize_gpx(document)
    result = sample_terrain_from_dem(
        data, path, vertical_datum="synthetic-datum", uncertainty_m=1,
        sampling_options=SamplingOptions(
            max_spacing_m=200, min_spacing_m=1
        ),
    )
    segment = result.sampling.segments[0]
    assert len(segment.points) > 2
    assert segment.complete
    assert all(point.dem_elevation_m == 100 for point in segment.points)
    assert segment.points[0].source_point_index == 0
    assert segment.points[-1].source_point_index == 1
    assert result.provenance.vertical_datum == "synthetic-datum"
    assert result.provenance.horizontal_crs == "EPSG:4326"
    assert result.provenance.uncertainty_m == 1
    assert result.sample_operations >= len(segment.points)
    assert serialize_gpx(document) == original


def test_bilinear_integration_interpolates_cell_centers(tmp_path):
    """The adapter uses F03 bilinear semantics rather than a second engine."""
    values = np.arange(256, dtype="float32").reshape(16, 16)
    path = make_dem(tmp_path, values=values)
    _, data = source([[(0.999, 0.001)]])
    result = sample_terrain_from_dem(
        data, path, dem_options=DEMOptions(method="bilinear")
    )
    assert result.sampling.segments[0].points[0].dem_elevation_m == pytest.approx(
        (values[0, 0] + values[0, 1] + values[1, 0] + values[1, 1]) / 4
    )
    assert result.provenance.method == "bilinear"


def test_projected_crs_transforms_wgs84_coordinates(tmp_path):
    """Projected raster samples use longitude-latitude input order."""
    path = make_dem(tmp_path, crs="EPSG:3857")
    transformer = Transformer.from_crs(
        "EPSG:3857", "EPSG:4326", always_xy=True
    )
    lon, lat = transformer.transform(450, 750)
    _, data = source([[(lat, lon)]])
    result = sample_terrain_from_dem(data, path)
    assert result.sampling.segments[0].points[0].dem_elevation_m == 100
    assert result.provenance.horizontal_crs == "EPSG:3857"


def test_nodata_and_out_of_bounds_are_unavailable(tmp_path):
    """Missing samples do not silently produce zero elevation or grade."""
    path = make_dem(tmp_path)
    with rasterio.open(path, "r+") as raster:
        values = raster.read(1)
        values[5, 1] = -9999
        raster.write(values, 1)
    _, data = source([[(.9945, .0015)], [(0, .5)]])
    result = sample_terrain_from_dem(data, path)
    assert all(not segment.complete for segment in result.sampling.segments)
    assert all(
        point.dem_elevation_m is None
        for segment in result.sampling.segments
        for point in segment.points
    )


def test_missing_units_rejected(tmp_path):
    """Do not infer metre elevation units from raster values."""
    path = make_dem(tmp_path, units="ft")
    _, data = source([[(.995, .001)]])
    with pytest.raises(DEMError, match="units"):
        sample_terrain_from_dem(data, path)


def test_missing_crs_rejected(tmp_path):
    """Reject ambiguous raster coordinate metadata."""
    path = make_dem(tmp_path, crs=None)
    _, data = source([[(.995, .001)]])
    with pytest.raises(DEMError, match="CRS"):
        sample_terrain_from_dem(data, path)


def test_sample_operation_budget_counts_intermediate_dem_probes(tmp_path):
    """Refinement midpoint calls count against the sampling budget."""
    path = make_dem(tmp_path)
    _, data = source([[(.995, .001), (.995, .012)]])
    with pytest.raises(DEMError, match="operation limit"):
        sample_terrain_from_dem(
            data, path, dem_options=DEMOptions(max_points=2),
        )


def test_file_size_budget_and_missing_file(tmp_path):
    """Honor F03 local-raster limits before opening file."""
    path = make_dem(tmp_path)
    _, data = source([[(.995, .001)]])
    with pytest.raises(DEMError, match="byte limit"):
        sample_terrain_from_dem(
            data, path, dem_options=DEMOptions(max_raster_bytes=1)
        )
    with pytest.raises(DEMError, match="does not exist"):
        sample_terrain_from_dem(data, tmp_path / "missing.tif")


def test_multiple_segments_no_connector_and_deterministic_json(tmp_path):
    """Segments are independent, metadata survives serialization."""
    path = make_dem(tmp_path)
    _, data = source([
        [(.995, .001), (.995, .005)],
        [(.996, .001), (.996, .005)],
    ])
    result = sample_terrain_from_dem(data, path)
    again = sample_terrain_from_dem(data, path)
    assert len(result.sampling.segments) == 2
    assert result.sampling.segments[1].points[0].distance_from_segment_start_m == 0
    assert dem_sampling_json(result) == dem_sampling_json(again)
    payload = json.loads(dem_sampling_json(result))
    assert payload["sampling"]["source_sha256"] == data.source_sha256
    assert payload["provenance"]["vertical_units"] == "m"
