"""NV-10 planned-versus-recorded boundary and missing-data contracts."""

from dataclasses import replace

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.planned_recorded import (
    ComparisonError, ComparisonOptions, compare_planned_recorded,
)


NS = "http://www.topografix.com/GPX/1/1"


def _dataset(body):
    """Create an immutable source-linked analytical dataset from GPX 1.1."""
    document = parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="nv10">'
         f"{body}</gpx>").encode(), strict=False,
    )
    return build_analytical_dataset(document, include_temporal=False)


def _track(coords):
    """Represent ordered recorded or planned track points."""
    return "<trk><trkseg>" + "".join(
        f'<trkpt lat="{lat}" lon="{lon}"/>'
        for lat, lon in coords
    ) + "</trkseg></trk>"


def test_single_planned_vertex_is_a_reference_feature():
    """Isolated reference geometry supports proximity without invented edges."""
    planned = _dataset(_track([(0, 0)]))
    recorded = _dataset(_track([(0, 0.001)]))
    result = compare_planned_recorded(
        planned, recorded, options=ComparisonOptions(tolerance_m=50),
    )
    assert len(result.matches) == 1
    assert not result.matches[0].near_planned
    assert result.matches[0].planned_edge_end is None
    assert result.matches[0].planned_edge_fraction is None
    assert result.max_deviation_m > 100


def test_empty_recorded_track_reports_unavailable_observations():
    """No track fixes must not imply zero deviation or full route coverage."""
    planned = _dataset(_track([(0, 0), (0, 0.001)]))
    recorded = _dataset("<trk><trkseg/></trk>")
    result = compare_planned_recorded(planned, recorded)
    assert "RECORDED_TRACK_UNAVAILABLE" in result.diagnostics
    assert result.sample_coverage_fraction is None
    assert result.max_deviation_m is None
    assert result.matches == ()


def test_reference_edge_budget_is_enforced():
    """Overlong source edges cannot enter bounded matching computations."""
    planned = _dataset(_track([(0, 0), (0, 1)]))
    recorded = _dataset(_track([(0, 0.5)]))
    with pytest.raises(ComparisonError, match="Reference edge exceeds"):
        compare_planned_recorded(
            planned, recorded,
            options=ComparisonOptions(max_reference_edge_m=1000),
        )


def test_consecutive_off_route_fixes_form_single_maximum_excursion():
    """A sustained divergence is one event, with greatest observed deviation."""
    planned = _dataset(_track([(0, 0), (0, 0.02)]))
    recorded = _dataset(_track([
        (0, 0), (0.003, 0.004), (0.01, 0.01), (0, 0.02),
    ]))
    result = compare_planned_recorded(
        planned, recorded, options=ComparisonOptions(tolerance_m=50),
    )
    assert len(result.excursions) == 1
    event = result.excursions[0]
    assert (event.start_point, event.end_point, event.rejoined) == (1, 2, True)
    assert event.maximum_deviation_m == pytest.approx(
        max(result.matches[1].deviation_m, result.matches[2].deviation_m)
    )
    assert result.matches[2].deviation_m > result.matches[1].deviation_m


def test_unknown_vertical_reference_never_produces_elevation_difference():
    """Even finite invented heights cannot establish datum compatibility."""
    planned = _dataset(_track([(0, 0), (0, 0.001)]))
    recorded = _dataset(_track([(0, 0.0005)]))
    altered_planned = replace(
        planned, dem_source="synthetic", dem_vertical_datum=None,
        points=tuple(replace(p, dem_elevation_m=100.) for p in planned.points),
        segments=tuple(replace(s, terrain_complete=True) for s in planned.segments),
    )
    altered_recorded = replace(
        recorded, dem_source="synthetic", dem_vertical_datum=None,
        points=tuple(replace(p, dem_elevation_m=110.) for p in recorded.points),
        segments=tuple(replace(s, terrain_complete=True) for s in recorded.segments),
    )
    result = compare_planned_recorded(altered_planned, altered_recorded)
    assert "ELEVATION_COMPARISON_UNAVAILABLE" in result.diagnostics
    assert all(m.elevation_difference_m is None for m in result.matches)
