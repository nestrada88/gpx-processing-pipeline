"""NV-17 compatible elevation interpolation and missing-data comparison tests."""

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.planned_recorded import compare_planned_recorded


NS = "http://www.topografix.com/GPX/1/1"


def _dataset(coords, heights, *, datum="synthetic-orthometric"):
    """Construct original geometry with separately identified derived DEM data."""
    points = "".join(
        f'<trkpt lat="{latitude}" lon="{longitude}"/>'
        for latitude, longitude in coords
    )
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="nv17">'
        f'<trk><trkseg>{points}</trkseg></trk></gpx>'
    ).encode()
    document = parse_gpx(xml, strict=False)
    dem = DEMResult(
        tuple(
            DEMSample(
                "track", 0, 0, i, height,
                "ok" if height is not None else "missing",
            )
            for i, height in enumerate(heights)
        ),
        DEMProvenance(
            "synthetic-test-surface", "EPSG:4326", datum,
            "m", (1.0, 1.0), "nearest", None,
        ),
    )
    return build_analytical_dataset(
        document, dem=dem, include_temporal=False,
    )


def test_compatible_dem_interpolates_reference_height_along_edge():
    """Compare a recorded midpoint to independently supplied reference heights."""
    planned = _dataset([(0, 0), (0, .002)], [100., 120.])
    recorded = _dataset([(0, .001)], [115.])
    result = compare_planned_recorded(planned, recorded)
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.near_planned
    assert match.planned_edge_fraction == pytest.approx(.5, abs=1e-6)
    assert match.elevation_difference_m == pytest.approx(5., abs=1e-5)
    assert "ELEVATION_COMPARISON_UNAVAILABLE" not in result.diagnostics


@pytest.mark.parametrize(
    "heights",
    [(None, 120.), (100., None)],
)
def test_missing_reference_endpoint_blocks_elevation_difference(heights):
    """Never replace a missing DEM endpoint with zero or interpolate across it."""
    planned = _dataset([(0, 0), (0, .002)], heights)
    recorded = _dataset([(0, .001)], [115.])
    result = compare_planned_recorded(planned, recorded)
    assert len(result.matches) == 1
    assert result.matches[0].elevation_difference_m is None
    assert "ELEVATION_COMPARISON_UNAVAILABLE" not in result.diagnostics


def test_distinct_vertical_datums_prohibit_numeric_elevation_comparison():
    """Numerically plausible heights from incompatible datums stay incomparable."""
    planned = _dataset(
        [(0, 0), (0, .002)], [100., 120.], datum="synthetic-a",
    )
    recorded = _dataset(
        [(0, .001)], [115.], datum="synthetic-b",
    )
    result = compare_planned_recorded(planned, recorded)
    assert result.matches[0].elevation_difference_m is None
    assert "ELEVATION_COMPARISON_UNAVAILABLE" in result.diagnostics
