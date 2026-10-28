"""Regression checks for F06 geodesic planned-versus-recorded matching."""

from dataclasses import replace
import json

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.planned_recorded import (
    ComparisonError, ComparisonOptions, compare_planned_recorded,
    planned_recorded_json,
)
from gpx_pipeline.waypoints import enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"


def dataset(segments, *, waypoints="", is_planned=False):
    """Construct track segments with independent source geometry and timing."""
    geometry = ""
    for segment in segments:
        points = "".join(
            f'<trkpt lat="{lat}" lon="{lon}"/>'
            for lat, lon in segment
        )
        geometry += f"<trkseg>{points}</trkseg>"
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="compare">'
        f'{waypoints}<trk>{geometry}</trk></gpx>'
    ).encode()
    doc = parse_gpx(xml, strict=False)
    catalog = (
        enrich_waypoints(doc, categories={0: "checkpoint"}, checkpoints={0: 1})
        if waypoints else None
    )
    return doc, build_analytical_dataset(
        doc, waypoints=catalog, include_temporal=False
    )


def test_differently_sampled_route_matches_geodesic_edges():
    """Mid-edge fixes must match without requiring equal vertex indices."""
    _, planned = dataset([[(0, 0), (0, 0.02)]])
    _, recorded = dataset([[(0, 0), (0, 0.005), (0, 0.01),
                            (0, 0.015), (0, 0.02)]])
    result = compare_planned_recorded(planned, recorded)
    assert len(result.matches) == 5
    assert all(match.near_planned for match in result.matches)
    assert result.max_deviation_m < 0.1
    assert result.distance_difference_m == pytest.approx(0, abs=0.01)
    assert result.sample_coverage_fraction == 1.0
    assert not result.excursions


def test_reversed_route_does_not_infer_direction():
    """Reverse traversals retain geometry proximity, not route-order claims."""
    _, planned = dataset([[(0, 0), (0, 0.01)]])
    _, recorded = dataset([[(0, 0.01), (0, 0)]])
    result = compare_planned_recorded(planned, recorded)
    assert all(match.near_planned for match in result.matches)
    assert result.max_deviation_m < 0.1


def test_divergence_and_rejoin_are_observed_point_events():
    """Isolated far-off fix marks an excursion, then subsequent rejoin."""
    _, planned = dataset([[(0, 0), (0, 0.02)]])
    _, recorded = dataset([[(0, 0), (0.01, 0.01), (0, 0.02)]])
    result = compare_planned_recorded(
        planned, recorded, options=ComparisonOptions(tolerance_m=100)
    )
    assert len(result.excursions) == 1
    event = result.excursions[0]
    assert (event.start_point, event.end_point, event.rejoined) == (1, 1, True)
    assert event.maximum_deviation_m > 1000


def test_segment_gap_does_not_create_rejoin():
    """Independent segments must not form an invented return event."""
    _, planned = dataset([[(0, 0), (0, 0.02)]])
    _, recorded = dataset([[(0.01, 0)], [(0, 0.02)]])
    result = compare_planned_recorded(
        planned, recorded, options=ComparisonOptions(tolerance_m=100)
    )
    assert len(result.excursions) == 1
    assert result.excursions[0].segment == 0
    assert not result.excursions[0].rejoined


def test_checkpoint_proximity_not_confirmed_visit():
    """Checkpoint association expresses proximity only, not completion."""
    waypoint = '<wpt lat="0" lon="0.005"><name>CP</name></wpt>'
    _, planned = dataset([[(0, 0), (0, 0.02)]], waypoints=waypoint)
    _, recorded = dataset([[(0, 0.005), (0, 0.007)]])
    result = compare_planned_recorded(planned, recorded)
    assert result.checkpoints[0].within_tolerance
    assert result.checkpoints[0].closest_recorded_vertex_m == 0


def test_empty_planned_geometry_reports_no_comparison():
    """Missing planned polyline makes proximity measurements unavailable."""
    _, planned = dataset([[]])
    _, recorded = dataset([[(0, 0), (0, 0.001)]])
    result = compare_planned_recorded(planned, recorded)
    assert not result.matches
    assert result.sample_coverage_fraction is None
    assert "PLANNED_GEOMETRY_UNAVAILABLE" in result.diagnostics


def test_partial_activity_and_deterministic_serialization():
    """Partial recordings do not incorrectly imply completed planned route."""
    _, planned = dataset([[(0, 0), (0, 0.02)]])
    _, recorded = dataset([[(0, 0), (0, 0.005)]])
    result = compare_planned_recorded(planned, recorded)
    assert result.recorded_distance_m < result.planned_distance_m
    assert result.sample_coverage_fraction == 1
    assert result.observed_elapsed_s is None
    assert result.duration_difference_s is None
    assert planned_recorded_json(result) == planned_recorded_json(
        compare_planned_recorded(planned, recorded)
    )
    assert json.loads(planned_recorded_json(result))["planned_sha256"]


def test_source_preservation():
    """Neither input source is changed by analysis."""
    doc_a, planned = dataset([[(0, 0), (0, 0.01)]])
    doc_b, recorded = dataset([[(0, 0.005), (0, 0.01)]])
    a, b = serialize_gpx(doc_a), serialize_gpx(doc_b)
    compare_planned_recorded(planned, recorded)
    assert serialize_gpx(doc_a) == a
    assert serialize_gpx(doc_b) == b


@pytest.mark.parametrize("options", [
    {"tolerance_m": -1}, {"tolerance_m": float("nan")},
    {"max_pairs": 0}, {"max_pairs": True},
    {"max_reference_edge_m": 0}, {"planned_duration_s": 0},
])
def test_invalid_configuration(options):
    """Invalid physical limits fail before analysis."""
    with pytest.raises(ValueError):
        ComparisonOptions(**options)


def test_pair_budget_enforced():
    """Bound quadratic matching costs for safety and reproducibility."""
    _, planned = dataset([[(0, 0), (0, 0.01), (0, 0.02)]])
    _, recorded = dataset([[(0, 0), (0, 0.01)]])
    with pytest.raises(ComparisonError, match="pair limit"):
        compare_planned_recorded(
            planned, recorded, options=ComparisonOptions(max_pairs=1)
        )
