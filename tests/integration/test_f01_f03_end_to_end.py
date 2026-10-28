"""End-to-end GPX -> F02 spatial -> DEM -> terrain regression cases."""

from math import isclose

import numpy as np
import rasterio
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.dem import DEMOptions, enrich_dem
from gpx_pipeline.spatial import validate_spatial
from gpx_pipeline.terrain import analyze_terrain

NS = "http://www.topografix.com/GPX/1/1"


def _make_dem(tmp_path):
    """Construct a deterministic WGS84 grid with metre elevations."""
    path = tmp_path / "terrain.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=4, height=4, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(-87, 14, 0.01, 0.01), nodata=-9999,
    ) as dataset:
        dataset.write(np.array([
            [100, 110, 120, 130],
            [200, 210, 220, 230],
            [300, 310, 320, 330],
            [400, 410, 420, 430],
        ], dtype="float32"), 1)
        dataset.set_band_unit(1, "m")
    return path


def _document():
    """Provide two segments and one missing-coverage waypoint."""
    body = (
        '<wpt lat="0" lon="0"><name>source waypoint</name></wpt>'
        '<trk><trkseg>'
        '<trkpt lat="13.995" lon="-86.995"><ele>999</ele></trkpt>'
        '<trkpt lat="13.995" lon="-86.985"><ele>999</ele></trkpt>'
        '<trkpt lat="13.995" lon="-86.975"><ele>999</ele></trkpt>'
        '</trkseg><trkseg>'
        '<trkpt lat="13.985" lon="-86.995"><ele>555</ele></trkpt>'
        '<trkpt lat="13.985" lon="-86.985"><ele>555</ele></trkpt>'
        '</trkseg></trk>'
    )
    source = (
        f'<gpx xmlns="{NS}" version="1.1" creator="integration">'
        f"{body}</gpx>"
    ).encode()
    return parse_gpx(source, strict=False)


def test_complete_processing_sequence(tmp_path):
    """Run the four domains together and verify immutable input geometry."""
    document = _document()
    original = serialize_gpx(document)

    spatial = validate_spatial(document)
    assert spatial.valid
    assert tuple(map(len, spatial.distances_m)) == (2, 1)
    assert all(
        distance > 0
        for segment in spatial.distances_m for distance in segment
    )

    dem = enrich_dem(
        document, _make_dem(tmp_path),
        vertical_datum="synthetic-local-reference",
        options=DEMOptions(method="nearest"),
    )
    track = [sample for sample in dem.samples if sample.kind == "track"]
    assert [sample.elevation_m for sample in track] == [
        100, 110, 120, 200, 210,
    ]
    waypoint = [sample for sample in dem.samples if sample.kind == "waypoint"]
    assert waypoint[0].status == "missing"

    analytics = analyze_terrain(document, dem)
    assert len(analytics.segments) == 2
    first, second = analytics.segments
    assert first.ascent_m == 20
    assert second.ascent_m == 10
    assert first.descent_m == second.descent_m == 0
    assert first.complete and second.complete
    assert first.coverage_fraction == second.coverage_fraction == 1.0
    assert first.horizontal_distance_m > second.horizontal_distance_m
    assert first.points[0].distance_m == 0
    assert second.points[0].distance_m == 0
    assert isclose(first.mean_m, 110.0)
    assert analytics.vertical_datum == "synthetic-local-reference"
    assert serialize_gpx(document) == original


def test_identical_inputs_produce_identical_outputs(tmp_path):
    """Check deterministic DEM and terrain outputs over repeated execution."""
    document = _document()
    raster = _make_dem(tmp_path)
    first_dem = enrich_dem(document, raster)
    second_dem = enrich_dem(document, raster)
    assert first_dem == second_dem
    assert analyze_terrain(document, first_dem) == analyze_terrain(
        document, second_dem
    )
