"""NV-14 terrain analysis validation of corrupted upstream numerical contracts."""

from math import nan
from types import SimpleNamespace

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.terrain import TerrainError, analyze_terrain


NS = "http://www.topografix.com/GPX/1/1"


def _document():
    """Create two geometrically valid input trackpoints."""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="nv14">'
         '<trk><trkseg><trkpt lat="0" lon="0"/>'
         '<trkpt lat="0" lon="0.001"/></trkseg></trk></gpx>'
        ).encode(), strict=False,
    )


def _dem():
    """Preserve one-to-one source point identity and explicit metre units."""
    return DEMResult(
        (
            DEMSample("track", 0, 0, 0, 100.0, "ok"),
            DEMSample("track", 0, 0, 1, 101.0, "ok"),
        ),
        DEMProvenance(
            "synthetic", "EPSG:4326", None, "m",
            (1.0, 1.0), "nearest", None,
        ),
    )


def test_terrain_rejects_invalid_upstream_spatial_status(monkeypatch):
    """Spatial validation failure prevents all terrain metrics."""
    import gpx_pipeline.terrain as terrain

    monkeypatch.setattr(
        terrain, "validate_spatial",
        lambda _source: SimpleNamespace(valid=False, distances_m=()),
    )
    with pytest.raises(TerrainError, match="F02 spatial validation failed"):
        analyze_terrain(_document(), _dem())


@pytest.mark.parametrize(
    ("distances", "expected"),
    [
        ((), "F02 segment identity mismatch"),
        (((),), "F02 edge count does not match segment"),
        (((nan,),), "F02 returned invalid horizontal distance"),
        (((-1.0,),), "F02 returned invalid horizontal distance"),
    ],
)
def test_terrain_rejects_corrupt_upstream_distance_arrays(
    monkeypatch, distances, expected,
):
    """Never calculate grade using mismatched or nonfinite source distances."""
    import gpx_pipeline.terrain as terrain

    monkeypatch.setattr(
        terrain, "validate_spatial",
        lambda _source: SimpleNamespace(valid=True, distances_m=distances),
    )
    with pytest.raises(TerrainError, match=expected):
        analyze_terrain(_document(), _dem())


def test_terrain_missing_heights_are_reported_not_interpolated():
    """A missing raster observation cannot produce fictitious elevation grade."""
    original = _dem()
    missing = DEMResult(
        (
            original.samples[0],
            DEMSample("track", 0, 0, 1, None, "missing"),
        ),
        original.provenance,
    )
    result = analyze_terrain(_document(), missing)
    assert result.segments[0].complete is False
    assert result.segments[0].points[1].elevation_m is None
    assert result.segments[0].points[1].grade_percent is None
    assert "TERRAIN_MISSING_ELEVATION" in {f.code for f in result.findings}
