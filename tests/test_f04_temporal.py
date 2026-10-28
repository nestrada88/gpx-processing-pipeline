"""F04 temporal chronology and kinematic reference tests."""

from datetime import timedelta

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.temporal import TemporalOptions, analyze_temporal

NS = "http://www.topografix.com/GPX/1/1"


def source(*segments):
    """Create GPX tracks from sequences of (longitude, timestamp) values."""
    parts = []
    for sequence in segments:
        points = []
        for longitude, timestamp in sequence:
            time_xml = f"<time>{timestamp}</time>" if timestamp is not None else ""
            points.append(
                f'<trkpt lat="0" lon="{longitude}">{time_xml}</trkpt>'
            )
        parts.append("<trkseg>" + "".join(points) + "</trkseg>")
    xml = (f'<gpx xmlns="{NS}" version="1.1" creator="temporal">'
           f'<trk>{"".join(parts)}</trk></gpx>').encode()
    return parse_gpx(xml, strict=False)


def test_utc_offsets_and_speed_reference():
    """Equivalent instants with different offsets yield correct duration."""
    document = source([
        (0, "2026-01-01T00:00:00Z"),
        (0.001, "2026-01-01T01:01:00+01:00"),
    ])
    before = serialize_gpx(document)
    result = analyze_temporal(document)
    edge = result.segments[0].edges[0]
    assert result.valid
    assert edge.elapsed_s == 60.0
    assert edge.distance_m == pytest.approx(111.319490793, rel=1e-6)
    assert edge.speed_m_s == pytest.approx(111.319490793 / 60, rel=1e-6)
    assert edge.pace_s_km == pytest.approx(60000 / 111.319490793, rel=1e-6)
    assert result.segments[0].complete
    assert serialize_gpx(document) == before


@pytest.mark.parametrize(
    ("next_time", "rule"),
    [
        ("2026-01-01T00:00:00Z", "DUPLICATE_TIMESTAMP"),
        ("2025-12-31T23:59:59Z", "REVERSED_TIMESTAMP"),
        ("2026-01-01T00:00:59", "INVALID_TIMESTAMP"),
        ("not-a-time", "INVALID_TIMESTAMP"),
    ],
)
def test_chronology_rejection(next_time, rule):
    """Invalid chronological ordering must never produce a speed."""
    document = source([
        (0, "2026-01-01T00:00:00Z"), (0.001, next_time),
    ])
    result = analyze_temporal(document)
    assert not result.valid
    assert any(f.code == rule for f in result.findings)
    assert result.segments[0].edges[0].speed_m_s is None


def test_missing_time_explicitly_incomplete():
    """Missing timestamps do not produce inferred edge velocities."""
    result = analyze_temporal(source([
        (0, "2026-01-01T00:00:00Z"), (0.001, None),
        (0.002, "2026-01-01T00:02:00Z"),
    ]))
    assert result.valid  # missing recorded time is a non-fatal coverage warning
    assert not result.segments[0].complete
    assert result.segments[0].elapsed_s is None
    assert all(edge.speed_m_s is None for edge in result.segments[0].edges)


def test_segment_boundaries_and_no_cross_segment_velocity():
    """Never connect timestamps or positions across track segments."""
    result = analyze_temporal(source(
        [(0, "2026-01-01T00:00:00Z"),
         (0.001, "2026-01-01T00:01:00Z")],
        [(5, "2026-01-01T00:01:00Z"),
         (5.001, "2026-01-01T00:02:00Z")],
    ))
    assert result.valid
    assert len(result.segments) == 2
    assert [len(s.edges) for s in result.segments] == [1, 1]
    assert [s.elapsed_s for s in result.segments] == [60, 60]


def test_speed_and_temporal_gap_warnings():
    """Threshold anomalies must remain warnings rather than fabricated fixes."""
    result = analyze_temporal(
        source([(0, "2026-01-01T00:00:00Z"),
                (1, "2026-01-01T00:00:01Z"),
                (1.001, "2026-01-01T01:00:01Z")]),
        options=TemporalOptions(speed_warning_m_s=10, gap_warning_s=300),
    )
    assert result.valid
    assert {finding.code for finding in result.findings} >= {
        "SPEED_ANOMALY", "TEMPORAL_GAP"
    }


def test_stationary_and_moving_statistics():
    """Zero displacement is stationary; valid travel counts as movement."""
    result = analyze_temporal(
        source([(0, "2026-01-01T00:00:00Z"),
                (0, "2026-01-01T00:01:00Z"),
                (0.001, "2026-01-01T00:02:00Z")])
    )
    segment = result.segments[0]
    assert segment.elapsed_s == 120
    assert segment.moving_s == 60
    assert segment.edges[0].speed_m_s == 0
    assert segment.edges[0].pace_s_km is None
    assert segment.moving_speed_m_s > segment.average_speed_m_s


def test_empty_and_single_point_segments():
    """Zero or one point never creates a fabricated movement edge."""
    result = analyze_temporal(source(
        [], [(0, "2026-01-01T00:00:00Z")]
    ))
    assert [len(s.edges) for s in result.segments] == [0, 0]
    assert all(s.elapsed_s == 0 for s in result.segments)


def test_fractional_seconds():
    """Preserve fractional-second elapsed time."""
    result = analyze_temporal(source([
        (0, "2026-01-01T00:00:00.250Z"),
        (0.001, "2026-01-01T00:00:01.750Z"),
    ]))
    assert result.segments[0].edges[0].elapsed_s == 1.5


def test_invalid_configuration():
    """Thresholds must be finite, positive quantities."""
    for value in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            TemporalOptions(speed_warning_m_s=value)
