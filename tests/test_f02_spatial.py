"""F02 spatial integrity regression and numerical reference tests."""

from math import isclose, isnan

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.spatial import (
    SpatialOptions,
    geodesic_distance_m,
    validate_spatial,
)

NS = "http://www.topografix.com/GPX/1/1"


def document(body: str):
    """Wrap a test fragment in a GPX document using the F01 parser."""
    xml = (
        f'<gpx xmlns="{NS}" version="1.1" creator="tests">'
        f"{body}</gpx>"
    ).encode()
    return parse_gpx(xml, strict=False)


@pytest.mark.parametrize(
    ("lat", "lon", "valid"),
    [
        ("-90", "-180", True),
        ("90", "180", True),
        ("0", "0", True),
        ("90.0001", "0", False),
        ("0", "180.1", False),
        ("NaN", "0", False),
        ("Infinity", "0", False),
        ("abc", "0", False),
    ],
)
def test_wgs84_bounds(lat, lon, valid):
    """Check coordinate boundary and invalid numeric inputs."""
    result = validate_spatial(
        document(f'<wpt lat="{lat}" lon="{lon}"/>')
    )
    assert result.valid is valid


def test_antimeridian_short_arc():
    """The 179-to-minus-179-degree transition crosses the dateline."""
    meters = geodesic_distance_m(0, 179, 0, -179)
    assert 222_000 < meters < 223_000


def test_reference_equator_distance():
    """WGS 84 geodesic 1-degree equatorial arc has known length."""
    meters = geodesic_distance_m(0, 0, 0, 1)
    assert isclose(meters, 111_319.49079327357, abs_tol=0.001)


def test_no_edges_between_track_segments():
    """Distinct GPX track segments have independent distance arrays."""
    result = validate_spatial(
        document(
            '<trk><trkseg><trkpt lat="0" lon="0"/>'
            '<trkpt lat="0" lon="1"/></trkseg>'
            '<trkseg><trkpt lat="20" lon="20"/></trkseg></trk>'
        )
    )
    assert [len(sequence) for sequence in result.distances_m] == [1, 0]


def test_invalid_point_does_not_bridge_gap():
    """An invalid intermediate point prevents both adjacent edges."""
    result = validate_spatial(
        document(
            '<trk><trkseg><trkpt lat="0" lon="0"/>'
            '<trkpt lat="100" lon="0"/>'
            '<trkpt lat="0" lon="2"/></trkseg></trk>'
        )
    )
    assert not result.valid
    assert len(result.distances_m[0]) == 2
    assert all(isnan(value) for value in result.distances_m[0])


def test_repeated_position_warns_without_rejecting():
    """Repeated coordinates are suspicious but remain valid geometry."""
    result = validate_spatial(
        document(
            '<trk><trkseg><trkpt lat="0" lon="0"/>'
            '<trkpt lat="0" lon="0"/></trkseg></trk>'
        )
    )
    assert result.valid
    assert result.distances_m == ((0.0,),)
    assert [finding.rule for finding in result.findings] == [
        "SPATIAL_DUPLICATE"
    ]


def test_jump_is_warning_and_optional():
    """Threshold diagnostics must not classify legitimate jumps as errors."""
    source = document(
        '<rte><rtept lat="0" lon="0"/><rtept lat="0" lon="1"/></rte>'
    )
    assert validate_spatial(source).valid
    result = validate_spatial(
        source, options=SpatialOptions(jump_warning_m=1000)
    )
    assert result.valid
    assert [finding.rule for finding in result.findings] == ["SPATIAL_JUMP"]


def test_elevation_finiteness():
    """Reject non-finite elevation while permitting omitted elevation."""
    result = validate_spatial(
        document('<wpt lat="0" lon="0"><ele>NaN</ele></wpt>')
    )
    assert not result.valid
    assert result.findings[0].rule == "SPATIAL_ELEVATION"


def test_non_mutation_and_determinism():
    """Spatial validation cannot alter XML bytes or ordering."""
    source = document(
        '<trk><trkseg><trkpt lat="12.123456789" lon="-86.100000001"/>'
        '<trkpt lat="12.123456789" lon="-86.100000001"/>'
        '</trkseg></trk>'
    )
    before = serialize_gpx(source)
    first = validate_spatial(source)
    second = validate_spatial(source)
    assert first == second
    assert serialize_gpx(source) == before


@pytest.mark.parametrize(
    "coords",
    [(91, 0, 0, 0), (0, -181, 0, 0), (0, 0, 0, float("inf"))],
)
def test_direct_geodesic_rejects_invalid_coordinates(coords):
    """Reject invalid coordinates for direct geodesic calculations."""
    with pytest.raises(ValueError):
        geodesic_distance_m(*coords)


def test_invalid_warning_thresholds():
    """Reject zero, negative, and non-finite anomaly thresholds."""
    for threshold in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            SpatialOptions(jump_warning_m=threshold)
