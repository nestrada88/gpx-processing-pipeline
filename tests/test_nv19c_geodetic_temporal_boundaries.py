"""NV-19C independent numerical input and temporal boundary regression tests."""

from math import inf, nan
from types import SimpleNamespace

import pytest
from lxml import etree

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.dem import _sample
from gpx_pipeline.temporal import _timestamp, analyze_temporal
from gpx_pipeline.terrain_sampling import terrain_adaptive_sample


NS = "http://www.topografix.com/GPX/1/1"


def _point(time_text):
    """Build a direct timestamp element without an upstream schema filter."""
    point = etree.Element(f"{{{NS}}}trkpt", lat="0", lon="0")
    time = etree.SubElement(point, f"{{{NS}}}time")
    time.text = time_text
    return point


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-02-30T12:00:00Z",
        "2026-13-01T00:00:00+00:00",
        "2026-10-29T25:00:00Z",
    ],
)
def test_calendar_invalidity_is_rejected_after_iso_shape_validation(stamp):
    """A regex-conforming impossible calendar instant must not be accepted."""
    with pytest.raises(ValueError, match="Invalid timestamp"):
        _timestamp(_point(stamp))


@pytest.mark.parametrize("x,y", [(nan, 0), (0, nan), (inf, 0), (0, -inf)])
def test_dem_rejects_nonfinite_projected_coordinates_before_raster_access(x, y):
    """An invalid transform input must never access or sample any DEM pixels."""
    class NoRasterAccess:
        @property
        def transform(self):
            raise AssertionError("invalid coordinates reached raster transform")

    value, status = _sample(NoRasterAccess(), x, y, "nearest")
    assert value is None
    assert status == "invalid_transform"


def _dataset():
    """Create a valid source track with no invented terrain observations."""
    document = parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="nv19c">'
         '<trk><trkseg><trkpt lat="0" lon="0"/>'
         '<trkpt lat="0" lon="0.001"/></trkseg></trk></gpx>').encode(),
        strict=False,
    )
    return document, build_analytical_dataset(
        document, include_temporal=False,
    )


@pytest.mark.parametrize(
    "callback, description, expected_exception, message",
    [
        (None, "synthetic DEM", TypeError, "sample_elevation_m must be callable"),
        (lambda _lat, _lon: 100., "", ValueError, "dem_source_description must be non-empty"),
    ],
)
def test_adaptive_sampling_rejects_invalid_dependency_contracts(
    callback, description, expected_exception, message,
):
    """Reject unavailable elevation providers or provenance before densifying."""
    document, data = _dataset()
    before = serialize_gpx(document)
    with pytest.raises(expected_exception, match=message):
        terrain_adaptive_sample(
            data, callback, dem_source_description=description,
        )
    assert serialize_gpx(document) == before


def test_missing_source_recorded_time_is_not_invented():
    """A source with no timestamp cannot acquire recorded elapsed time."""
    document, _ = _dataset()
    before = serialize_gpx(document)
    report = analyze_temporal(document)
    assert report.segments[0].elapsed_s is None
    assert serialize_gpx(document) == before
