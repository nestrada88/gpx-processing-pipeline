"""Adversarial contracts for risk-ranked uncovered numerical error branches."""

from dataclasses import replace
from math import nan
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from pyproj.exceptions import ProjError
from rasterio.transform import from_origin

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import DEMError, DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.dem_sampling_adapter import sample_terrain_from_dem
from gpx_pipeline.route_analysis import RouteAnalysisError, analyze_route
from gpx_pipeline.terrain import TerrainError, analyze_terrain


NS = "http://www.topografix.com/GPX/1/1"


def _document():
    """Use two valid original vertices; only derived data is corrupted."""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="adversarial">'
         '<trk><trkseg><trkpt lat="0.5" lon="0.5"/>'
         '<trkpt lat="0.5" lon="0.501"/></trkseg></trk></gpx>').encode(),
        strict=False,
    )


def _raster(tmp_path):
    """Create a small local one-band, metric-height DEM."""
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=4, height=4, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(0, 1, .25, .25), nodata=-9999,
    ) as raster:
        raster.write(np.full((4, 4), 100, dtype=np.float32), 1)
        raster.set_band_unit(1, "m")
    return path


def _dem(*, heights=(100.0, 101.0), units="m"):
    """Build index-matched samples with explicit, independently set metadata."""
    samples = tuple(
        DEMSample("track", 0, 0, index, value, "ok")
        for index, value in enumerate(heights)
    )
    provenance = DEMProvenance(
        "synthetic", "EPSG:4326", None, units,
        (1.0, 1.0), "nearest", None,
    )
    return DEMResult(samples, provenance)


def test_adapter_maps_projection_failure_to_typed_dem_error(tmp_path, monkeypatch):
    """A failed PROJ transform never produces an invented elevation."""
    from gpx_pipeline import dem_sampling_adapter as adapter

    class FailingTransformer:
        def transform(self, *_args, **_kwargs):
            raise ProjError("synthetic projection failure")

    monkeypatch.setattr(
        adapter.Transformer, "from_crs",
        lambda *_args, **_kwargs: FailingTransformer(),
    )
    dataset = build_analytical_dataset(_document(), include_temporal=False)
    with pytest.raises(DEMError, match="DEM coordinate transformation failed"):
        sample_terrain_from_dem(dataset, _raster(tmp_path))


@pytest.mark.parametrize(
    ("coordinate", "expected"),
    [
        ((nan, 0.5), "Nonfinite sample coordinates"),
        ((91.0, 0.5), "Sample coordinates outside WGS 84 bounds"),
    ],
)
def test_adapter_rejects_corrupt_derived_coordinates(
    tmp_path, monkeypatch, coordinate, expected,
):
    """Inject invalid interpolated coordinates after source validation."""
    from gpx_pipeline import dem_sampling_adapter as adapter

    def inject_coordinate(_dataset, callback, **_kwargs):
        callback(*coordinate)
        raise AssertionError("Invalid sample coordinate was accepted")

    monkeypatch.setattr(adapter, "terrain_adaptive_sample", inject_coordinate)
    dataset = build_analytical_dataset(_document(), include_temporal=False)
    with pytest.raises(DEMError, match=expected):
        sample_terrain_from_dem(dataset, _raster(tmp_path))


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"point": 3}, "Segment point indices are not contiguous"),
        ({"dem_elevation_m": 15.0}, "Terrain fields lack a terrain source"),
        ({"elapsed_from_previous_s": 60.0}, "Timing fields lack a temporal source"),
    ],
)
def test_route_analysis_rejects_inconsistent_derived_fields(changes, expected):
    """Fail closed when an analytical row contradicts its segment contract."""
    dataset = build_analytical_dataset(_document(), include_temporal=False)
    points = list(dataset.points)
    points[1] = replace(points[1], **changes)
    with pytest.raises(RouteAnalysisError, match=expected):
        analyze_route(replace(dataset, points=tuple(points)))


@pytest.mark.parametrize(
    ("speed", "duration", "expected"),
    [
        (None, 60.0, "Inconsistent kinematic edge fields"),
        (1.0, -1.0, "Invalid elapsed time or speed"),
        (1.0, 60.0, "Kinematics do not match geodesic distance"),
    ],
)
def test_route_analysis_rejects_untrustworthy_motion(
    speed, duration, expected,
):
    """Inconsistent measured speed and elapsed time cannot reach route totals."""
    dataset = build_analytical_dataset(_document(), include_temporal=False)
    points = list(dataset.points)
    points[1] = replace(
        points[1], observed_speed_m_s=speed,
        elapsed_from_previous_s=duration,
    )
    segment = replace(dataset.segments[0], timing_complete=True)
    with pytest.raises(RouteAnalysisError, match=expected):
        analyze_route(replace(
            dataset, points=tuple(points), segments=(segment,),
        ))


def test_route_analysis_cannot_claim_complete_terrain_with_missing_height():
    """Unknown DEM height remains unknown, not complete elevation coverage."""
    dataset = build_analytical_dataset(_document(), include_temporal=False)
    segment = replace(dataset.segments[0], terrain_complete=True)
    with pytest.raises(RouteAnalysisError, match="Terrain marked complete"):
        analyze_route(replace(dataset, segments=(segment,)))


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_dem(units="ft"), "DEM elevation units must be metres"),
        (_dem(heights=(100.0, nan)), "Invalid finite DEM elevation"),
        (
            DEMResult(
                (DEMSample("track", 0, 0, 0, 100.0, "ok"),),
                _dem().provenance,
            ),
            "DEM sample identities do not match GPX points",
        ),
    ],
)
def test_terrain_rejects_malformed_upstream_dem(result, expected):
    """Invalid provenance or source-sample alignment cannot become a profile."""
    with pytest.raises(TerrainError, match=expected):
        analyze_terrain(_document(), result)


def test_terrain_zero_horizontal_distance_has_undefined_grade():
    """A vertical height difference at the same position is not a slope."""
    document = parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="adversarial">'
         '<trk><trkseg><trkpt lat="0" lon="0"/>'
         '<trkpt lat="0" lon="0"/></trkseg></trk></gpx>').encode(),
        strict=False,
    )
    result = analyze_terrain(document, _dem())
    segment = result.segments[0]
    assert segment.points[1].grade_percent is None
    assert segment.horizontal_distance_m == 0
    assert "TERRAIN_ZERO_DISTANCE" in {f.code for f in result.findings}
