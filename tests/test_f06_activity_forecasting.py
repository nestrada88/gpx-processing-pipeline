"""F06 timing forecast numerical and integration regression tests."""

from datetime import datetime, timezone
from math import isclose
import json

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.activity_forecasting import (
    ForecastOptions, activity_forecast_json, forecast_activity,
    tobler_speed_kmh,
)
from gpx_pipeline.dem import DEMProvenance, DEMResult, DEMSample
from gpx_pipeline.waypoints import enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"


def fixture(*, heights=(100., 100., 100.), checkpoints=False):
    """Create a two-edge GPX track with explicit DEM elevations."""
    points = "".join(
        f'<trkpt lat="0" lon="{lon}"/>'
        for lon in (0, 0.001, 0.002)
    )
    waypoint = (
        '<wpt lat="0" lon="0.001"><name>Mid</name></wpt>'
        if checkpoints else ""
    )
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="forecast">'
        f'{waypoint}<trk><trkseg>{points}</trkseg></trk></gpx>'
    ).encode()
    document = parse_gpx(xml, strict=False)
    samples = [
        DEMSample("track", 0, 0, i, value,
                  "ok" if value is not None else "missing")
        for i, value in enumerate(heights)
    ]
    if checkpoints:
        samples.insert(0, DEMSample("waypoint", 0, None, 0, 100., "ok"))
    dem = DEMResult(tuple(samples), DEMProvenance(
        "synthetic", "EPSG:4326", "local", "m",
        (1., 1.), "nearest", None,
    ))
    catalog = enrich_waypoints(
        document, categories={0: "checkpoint"}, checkpoints={0: 1},
    ) if checkpoints else None
    return document, build_analytical_dataset(
        document, dem=dem, waypoints=catalog, include_temporal=False,
    )


def test_tobler_reference_and_gradient_sign():
    """Validate standard Tobler functional values and slope sensitivity."""
    assert tobler_speed_kmh(-5.) == pytest.approx(6.)
    assert tobler_speed_kmh(0.) == pytest.approx(
        6 * __import__("math").exp(-0.175)
    )
    assert tobler_speed_kmh(20.) < tobler_speed_kmh(0.)
    assert tobler_speed_kmh(-20.) < tobler_speed_kmh(-5.)


def test_flat_forecast_duration_and_scenario_order():
    """Time equals WGS84 distance divided by nominal model speed."""
    _, data = fixture()
    result = forecast_activity(data)
    nominal = result.scenarios[1]
    speed = tobler_speed_kmh(0)
    expected = result.segments[0].distance_m * 3.6 / speed
    assert nominal.moving_s == pytest.approx(expected)
    assert result.segments[0].complete
    assert [s.elapsed_s for s in result.scenarios] == pytest.approx(
        [expected * 0.8, expected, expected * 1.3]
    )
    assert nominal.finish_time is None


def test_climb_and_descent_are_not_flat():
    """Signed DEM grades affect predictions independently per edge."""
    _, data = fixture(heights=(100., 120., 100.))
    result = forecast_activity(data)
    uphill, downhill = result.edges
    assert uphill.grade_percent > 0
    assert downhill.grade_percent < 0
    assert uphill.predicted_speed_kmh < tobler_speed_kmh(0)
    assert downhill.predicted_speed_kmh is not None
    assert result.segments[0].moving_s == pytest.approx(
        uphill.predicted_moving_s + downhill.predicted_moving_s
    )


def test_missing_grade_unavailable_and_explicit_assumption():
    """Never silently equate missing DEM height with flat terrain."""
    _, data = fixture(heights=(100., None, 100.))
    absent = forecast_activity(data)
    assert absent.scenarios[1].moving_s is None
    assert "INCOMPLETE_FORECAST" in absent.diagnostics
    assumed = forecast_activity(
        data, options=ForecastOptions(missing_grade="assume")
    )
    assert assumed.scenarios[1].moving_s is not None
    assert "ASSUMED_GRADE_USED" in assumed.diagnostics
    assert all(edge.grade_assumed for edge in assumed.edges)


def test_rest_start_timestamp_checkpoint_without_false_rest_allocation():
    """Expose exact-vertex checkpoint ETA and separately modeled rest."""
    _, data = fixture(checkpoints=True)
    options = ForecastOptions(
        rest_seconds=600,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    result = forecast_activity(data, options=options)
    checkpoint = result.checkpoints[0]
    assert checkpoint.point == 1
    assert checkpoint.elapsed_s == pytest.approx(
        result.edges[0].predicted_moving_s
    )
    assert checkpoint.arrival_time.endswith("Z")
    assert result.scenarios[1].elapsed_s == pytest.approx(
        result.scenarios[1].moving_s + 600
    )
    assert "REST_NOT_ALLOCATED_TO_CHECKPOINTS" in result.diagnostics
    assert result.scenarios[1].finish_time is not None


def test_source_immutability_json_determinism():
    """Forecast never overwrites recorded or DEM values."""
    document, data = fixture()
    baseline = serialize_gpx(document)
    first = forecast_activity(data)
    second = forecast_activity(data)
    assert activity_forecast_json(first) == activity_forecast_json(second)
    assert json.loads(activity_forecast_json(first))["model"] == "tobler"
    assert serialize_gpx(document) == baseline


@pytest.mark.parametrize("options", [
    {"min_speed_kmh": 0},
    {"min_speed_kmh": float("nan")},
    {"min_speed_kmh": 10, "max_speed_kmh": 8},
    {"rest_seconds": -1},
    {"optimistic_factor": 1.1},
    {"conservative_factor": 0.9},
    {"missing_grade": "flat"},
    {"start_time": datetime(2026, 1, 1)},
])
def test_invalid_options(options):
    """Reject physically invalid and timezone-naive input."""
    with pytest.raises(ValueError):
        ForecastOptions(**options)


def test_zero_distance_edge_does_not_divide_by_zero():
    """Repeated coordinate points require zero duration."""
    _, data = fixture()
    from dataclasses import replace
    points = list(data.points)
    second = replace(
        points[1], longitude=points[0].longitude,
        cumulative_distance_m=0., grade_percent=None,
    )
    third = replace(
        points[2], cumulative_distance_m=points[2].cumulative_distance_m -
        points[1].cumulative_distance_m,
    )
    segments = (replace(
        data.segments[0],
        horizontal_distance_m=third.cumulative_distance_m,
    ),)
    modified = replace(data, points=(points[0], second, third), segments=segments)
    output = forecast_activity(modified)
    assert output.edges[0].predicted_moving_s == 0.
