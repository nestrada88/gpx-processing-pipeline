"""F05 waypoint catalog identity, proximity and resilience tests."""

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.waypoints import WaypointError, enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"


def fixture(waypoints=True, route=True):
    """Build a GPX input with preserved labels and spatial geometry."""
    wpt = (
        '<wpt lat="12" lon="-86"><name>Start</name>'
        '<desc>Field observation</desc><sym>Flag</sym>'
        '<type>Custom</type></wpt>'
        '<wpt lat="12.5" lon="-86.5"><name>Remote</name></wpt>'
        if waypoints else ""
    )
    trk = (
        '<trk><trkseg><trkpt lat="12" lon="-86"/>'
        '<trkpt lat="12.01" lon="-86"/></trkseg></trk>'
        if route else ""
    )
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="tests">'
         f"{wpt}{trk}</gpx>").encode(), strict=False
    )


def test_source_metadata_classification_and_checkpoints():
    """Classification and checkpoint ordering never rewrite GPX."""
    source = fixture()
    original = serialize_gpx(source)
    catalog = enrich_waypoints(
        source, categories={0: "checkpoint", 1: "hazard"},
        checkpoints={0: 1, 1: 2},
    )
    first, second = catalog.entries
    assert first.name == "Start"
    assert first.description == "Field observation"
    assert first.symbol == "Flag"
    assert first.recorded_type == "Custom"
    assert first.checkpoint_order == 1
    assert second.checkpoint_order == 2
    assert second.category == "hazard"
    assert "user:classification" in second.provenance
    assert serialize_gpx(source) == original


def test_vertex_distance_and_near_route_threshold():
    """Near-route means proximity to a recorded vertex, not trail segment."""
    first, second = enrich_waypoints(
        fixture(), proximity_threshold_m=50
    ).entries
    assert first.nearest_vertex_m == 0
    assert first.near_route
    assert second.nearest_vertex_m > 50
    assert not second.near_route


def test_empty_route_has_unknown_proximity():
    """No route geometry must not be interpreted as a distant route."""
    catalog = enrich_waypoints(fixture(route=False))
    assert all(entry.nearest_vertex_m is None for entry in catalog.entries)
    assert all(entry.near_route is None for entry in catalog.entries)
    assert [finding.code for finding in catalog.findings] == [
        "NO_ROUTE_VERTICES", "NO_ROUTE_VERTICES"
    ]


def test_optional_geocoder_and_failure_isolation():
    """Geocoding failure is explicit while original waypoint remains usable."""
    source = fixture()
    result = enrich_waypoints(
        source, reverse_geocoder=lambda lat, lon: (
            "Test place" if lat == 12 else 1
        )
    )
    assert result.entries[0].place_label == "Test place"
    assert result.entries[1].place_label is None
    assert result.findings[0].code == "GEOCODING_FAILED"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"categories": {2: "unknown"}},
        {"categories": {0: ""}},
        {"checkpoints": {2: 1}},
        {"checkpoints": {0: 1, 1: 1}},
        {"checkpoints": {0: 0}},
        {"checkpoints": {0: True}},
        {"proximity_threshold_m": float("nan")},
        {"proximity_threshold_m": -1},
    ],
)
def test_invalid_configuration_rejected(kwargs):
    """Fail closed on invalid taxonomy and checkpoint identifiers."""
    with pytest.raises((ValueError, WaypointError)):
        enrich_waypoints(fixture(), **kwargs)


def test_invalid_spatial_rejected():
    """Require F02 validation before geospatial annotation."""
    source = parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="test">'
         '<wpt lat="91" lon="-86"/></gpx>').encode(), strict=False
    )
    with pytest.raises(WaypointError, match="F02"):
        enrich_waypoints(source)


def test_repeatable_catalog_and_unclassified_default():
    """No classification is guessed from names or symbols."""
    source = fixture()
    a = enrich_waypoints(source)
    b = enrich_waypoints(source)
    assert a == b
    assert all(entry.category == "unclassified" for entry in a.entries)
