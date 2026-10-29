"""NV-04 independently calculated time, kinematics and forecast contracts."""

from datetime import datetime, timezone
from math import exp, isclose

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.activity_forecasting import (
    ForecastOptions, forecast_activity, tobler_speed_kmh,
)
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.spatial import geodesic_distance_m
from gpx_pipeline.temporal import TemporalOptions, analyze_temporal


NS = "http://www.topografix.com/GPX/1/1"
EQUATORIAL_DEGREE_M = 111_319.49079327357


def _source(*vertices):
    """Build a single immutable segment from (longitude, ISO time) pairs."""
    points = "".join(
        f'<trkpt lat="0" lon="{lon}">'
        + (f"<time>{stamp}</time>" if stamp is not None else "")
        + "</trkpt>"
        for lon, stamp in vertices
    )
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="nv04">'
        f"<trk><trkseg>{points}</trkseg></trk></gpx>"
    ).encode()
    return parse_gpx(xml, strict=False)


def test_timezone_equivalence_fractional_elapsed_and_independent_speed():
    """Offsets represent instants; expected distance is a fixed WGS84 constant."""
    source = _source(
        (0, "2026-01-01T00:00:00.250Z"),
        (.001, "2026-01-01T01:01:00.750+01:00"),
    )
    original = serialize_gpx(source)
    result = analyze_temporal(source)
    edge = result.segments[0].edges[0]
    distance = EQUATORIAL_DEGREE_M / 1000
    assert result.valid and result.segments[0].complete
    assert edge.elapsed_s == 60.5
    assert isclose(edge.distance_m, distance, rel_tol=0, abs_tol=.001)
    assert isclose(edge.speed_m_s, distance / 60.5, rel_tol=0, abs_tol=2e-5)
    assert isclose(edge.pace_s_km, 1000 * 60.5 / distance, rel_tol=1e-8)
    assert serialize_gpx(source) == original


@pytest.mark.parametrize(
    ("later", "code"),
    [
        ("2026-01-01T00:00:00Z", "DUPLICATE_TIMESTAMP"),
        ("2025-12-31T23:59:59Z", "REVERSED_TIMESTAMP"),
        ("2026-01-01T00:00:01", "INVALID_TIMESTAMP"),
    ],
)
def test_bad_chronology_never_invents_finite_speed(later, code):
    """Nonpositive or invalid intervals cannot be treated as movement rates."""
    result = analyze_temporal(_source(
        (0, "2026-01-01T00:00:00Z"), (.001, later)
    ))
    assert not result.valid
    assert code in {finding.code for finding in result.findings}
    assert result.segments[0].edges[0].speed_m_s is None
    assert result.segments[0].edges[0].pace_s_km is None
    assert result.segments[0].elapsed_s is None


def test_warning_threshold_does_not_invalidate_recorded_arithmetic():
    """An implausible speed is a warning, not a numerical alteration."""
    result = analyze_temporal(
        _source(
            (0, "2026-01-01T00:00:00Z"),
            (.001, "2026-01-01T00:00:01Z"),
        ),
        options=TemporalOptions(speed_warning_m_s=5),
    )
    edge = result.segments[0].edges[0]
    assert result.valid
    assert "SPEED_ANOMALY" in {f.code for f in result.findings}
    assert isclose(edge.speed_m_s, EQUATORIAL_DEGREE_M / 1000, abs_tol=.001)
    assert edge.elapsed_s == 1.0


@pytest.mark.parametrize("grade", [-20.0, -5.0, 0.0, 10.0, 40.0])
def test_tobler_independent_equation_and_bounds(grade):
    """Compare bounded public model to direct evaluation of its equation."""
    raw_speed = 6.0 * exp(-3.5 * abs(grade / 100.0 + .05))
    expected = min(8.0, max(.3, raw_speed))
    assert isclose(
        tobler_speed_kmh(grade), expected, rel_tol=1e-14, abs_tol=1e-14
    )


def test_forecast_explicit_flat_assumption_and_scenario_time_arithmetic():
    """Model time from a fixed equatorial distance without DEM observations."""
    document = _source((0, None), (.001, None), (.002, None))
    dataset = build_analytical_dataset(document, include_temporal=False)
    missing = forecast_activity(dataset)
    assert missing.scenarios[1].elapsed_s is None
    assert "GRADE_UNAVAILABLE" in missing.diagnostics
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    options = ForecastOptions(
        missing_grade="assume", assumed_grade_percent=0,
        start_time=start, rest_seconds=120,
    )
    output = forecast_activity(dataset, options=options)
    speed = 6.0 * exp(-.175)
    expected_moving_s = (2 * EQUATORIAL_DEGREE_M / 1000) * 3.6 / speed
    nominal = output.scenarios[1]
    assert all(e.grade_assumed for e in output.edges)
    assert "ASSUMED_GRADE_USED" in output.diagnostics
    assert isclose(nominal.moving_s, expected_moving_s, abs_tol=.001)
    assert isclose(nominal.elapsed_s, expected_moving_s + 120, abs_tol=.001)
    assert [s.label for s in output.scenarios] == [
        "optimistic", "nominal", "conservative"
    ]
    assert output.scenarios[0].elapsed_s <= nominal.elapsed_s
    assert nominal.elapsed_s <= output.scenarios[2].elapsed_s
    assert nominal.finish_time.endswith("Z")
    assert output.source_sha256 == dataset.source_sha256
    assert serialize_gpx(document) == document.xml
