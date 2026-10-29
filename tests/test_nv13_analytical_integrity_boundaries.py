"""NV-13 canonical analytical fail-closed regression contracts."""

from dataclasses import replace
from math import nan

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.route_analysis import RouteAnalysisError, analyze_route
from gpx_pipeline.waypoints import enrich_waypoints


NS = "http://www.topografix.com/GPX/1/1"


def _dataset(*, waypoint=False):
    """Build ordinary, immutable GPX geometry before corrupting derived rows."""
    wpt = '<wpt lat="0" lon="0"><name>CP</name></wpt>' if waypoint else ""
    document = parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="nv13">'
         f"{wpt}<trk><trkseg>"
         '<trkpt lat="0" lon="0"/><trkpt lat="0" lon="0.001"/>'
         "</trkseg></trk></gpx>").encode(),
        strict=False,
    )
    catalog = enrich_waypoints(document) if waypoint else None
    return build_analytical_dataset(
        document, waypoints=catalog, include_temporal=False
    )


def test_nonfinite_derived_dem_is_rejected_even_when_terrain_incomplete():
    """A NaN cannot become a published route elevation summary."""
    data = _dataset()
    points = list(data.points)
    points[1] = replace(points[1], dem_elevation_m=nan)
    segments = (replace(data.segments[0], terrain_complete=False),)
    with pytest.raises(RouteAnalysisError, match="Non-finite DEM elevation"):
        analyze_route(replace(data, points=tuple(points), segments=segments))


def test_complete_temporal_flag_requires_every_edge_to_be_timed():
    """An unsupported complete flag must not advertise elapsed route timing."""
    data = _dataset()
    segments = (replace(data.segments[0], timing_complete=True),)
    with pytest.raises(RouteAnalysisError, match="Timing marked complete"):
        analyze_route(replace(data, segments=segments))


def test_unknown_analytical_point_kind_fails_closed():
    """Unrecognized geometry classifications cannot enter route statistics."""
    data = _dataset()
    points = list(data.points)
    points[1] = replace(points[1], kind="synthetic-unknown")
    with pytest.raises(RouteAnalysisError, match="Unknown geometry point type"):
        analyze_route(replace(data, points=tuple(points)))


def test_waypoint_catalog_identity_must_match_source_point_identity():
    """A foreign derived waypoint identity must not pass reconciliation."""
    data = _dataset(waypoint=True)
    original = data.waypoint_catalog.entries[0]
    invalid = replace(original, index=11)
    catalog = replace(data.waypoint_catalog, entries=(invalid,))
    with pytest.raises(RouteAnalysisError, match="Waypoint catalog indices"):
        analyze_route(replace(data, waypoint_catalog=catalog))
