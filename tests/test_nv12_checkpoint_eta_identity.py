"""NV-12 checkpoint ETA identity, missing-grade, and segment contracts."""

from datetime import datetime, timezone

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.activity_forecasting import ForecastOptions, forecast_activity
from gpx_pipeline.waypoints import enrich_waypoints


NS = "http://www.topografix.com/GPX/1/1"


def _dataset(*, vertices, checkpoint):
    """Build an immutable WGS84 analytical dataset with one ordered checkpoint."""
    points = "".join(
        f'<trkpt lat="{lat}" lon="{lon}"/>'
        for lat, lon in vertices
    )
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="nv12">'
        f'<wpt lat="{checkpoint[0]}" lon="{checkpoint[1]}">'
        '<name>Checkpoint</name></wpt>'
        f'<trk><trkseg>{points}</trkseg></trk></gpx>'
    ).encode()
    document = parse_gpx(xml, strict=False)
    catalog = enrich_waypoints(
        document, categories={0: "checkpoint"}, checkpoints={0: 1}
    )
    data = build_analytical_dataset(
        document, waypoints=catalog, include_temporal=False
    )
    return document, data


def test_ambiguous_checkpoint_vertex_never_gets_arbitrary_eta():
    """Repeated coordinates cannot be resolved by first-hit matching."""
    doc, data = _dataset(
        vertices=[(0, 0), (0, .001), (0, .001), (0, .002)],
        checkpoint=(0, .001),
    )
    before = serialize_gpx(doc)
    result = forecast_activity(
        data, options=ForecastOptions(
            missing_grade="assume",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    assert result.checkpoints == ()
    assert "CHECKPOINT_POSITION_AMBIGUOUS" in result.diagnostics
    assert serialize_gpx(doc) == before


def test_missing_grade_blocks_checkpoint_eta_without_simulating_time():
    """A unique checkpoint must not inherit timing across unavailable edges."""
    _, data = _dataset(
        vertices=[(0, 0), (0, .001), (0, .002)],
        checkpoint=(0, .002),
    )
    result = forecast_activity(
        data, options=ForecastOptions(
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    assert result.checkpoints == ()
    assert "CHECKPOINT_ETA_UNAVAILABLE" in result.diagnostics
    assert "INCOMPLETE_FORECAST" in result.diagnostics
    assert "GRADE_UNAVAILABLE" in result.diagnostics
    assert result.scenarios[1].finish_time is None


def test_checkpoint_exact_vertex_eta_has_no_unallocated_route_rest():
    """Checkpoint ETA reflects simulated movement, not undistributed rest."""
    _, data = _dataset(
        vertices=[(0, 0), (0, .001), (0, .002)],
        checkpoint=(0, .001),
    )
    options = ForecastOptions(
        missing_grade="assume", rest_seconds=120,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    result = forecast_activity(data, options=options)
    assert len(result.checkpoints) == 1
    checkpoint = result.checkpoints[0]
    assert checkpoint.point == 1
    assert checkpoint.elapsed_s == pytest.approx(
        result.edges[0].predicted_moving_s
    )
    assert checkpoint.arrival_time.endswith("Z")
    assert "REST_NOT_ALLOCATED_TO_CHECKPOINTS" in result.diagnostics
    assert result.scenarios[1].elapsed_s == pytest.approx(
        result.scenarios[1].moving_s + 120
    )
