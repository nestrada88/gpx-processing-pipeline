"""NV-01 independent WGS 84 references and segment-safe invariants.

Reference constants are fixed values for WGS 84 (a = 6378137 m,
inverse flattening = 298.257223563). Expected numerical results do not call
the implementation's GeographicLib inverse as their oracle.
"""

from math import fsum, isclose, isfinite

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.spatial import geodesic_distance_m, validate_spatial


NS = "http://www.topografix.com/GPX/1/1"
ABS_TOLERANCE_M = 0.001


def _document(body: str):
    """Build independent GPX sequences without altering serialized values."""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="nv01">'
         f"{body}</gpx>").encode("utf-8"),
        strict=False,
    )


@pytest.mark.parametrize(
    ("first", "last", "expected_m"),
    [
        ((0.0, 0.0), (0.0, 1.0), 111_319.49079327357),
        ((0.0, 0.0), (1.0, 0.0), 110_574.38855779878),
        ((0.0, 179.0), (0.0, -179.0), 222_638.98158654713),
        ((90.0, 0.0), (-90.0, 0.0), 20_003_931.458625447),
    ],
)
def test_wgs84_fixed_reference_distances(first, last, expected_m):
    """Compare ellipsoidal distances to independently fixed WGS 84 values."""
    measured = geodesic_distance_m(*first, *last)
    assert isfinite(measured) and measured >= 0
    assert isclose(measured, expected_m, rel_tol=0.0, abs_tol=ABS_TOLERANCE_M)
    assert isclose(
        geodesic_distance_m(*last, *first),
        expected_m,
        rel_tol=0.0,
        abs_tol=ABS_TOLERANCE_M,
    )


@pytest.mark.parametrize(
    "position",
    [(0.0, 0.0), (90.0, 180.0), (-90.0, -180.0), (12.123456, -86.123456)],
)
def test_identical_coordinates_have_zero_distance(position):
    """Coincident coordinates must have zero length, including at poles."""
    assert geodesic_distance_m(*position, *position) == 0.0


def test_source_segment_and_route_distances_use_only_their_own_edges():
    """A distant segment, waypoint and route must not add connecting edges."""
    source = _document(
        '<wpt lat="40" lon="40"/>'
        '<trk><trkseg>'
        '<trkpt lat="0" lon="0"/><trkpt lat="0" lon="1"/>'
        '<trkpt lat="0" lon="2"/>'
        '</trkseg><trkseg>'
        '<trkpt lat="20" lon="20"/><trkpt lat="20" lon="20"/>'
        '</trkseg></trk>'
        '<rte><rtept lat="0" lon="179"/><rtept lat="0" lon="-179"/></rte>'
    )
    original = serialize_gpx(source)
    result = validate_spatial(source)
    assert result.valid
    assert tuple(map(len, result.distances_m)) == (2, 1, 1)
    assert isclose(
        fsum(result.distances_m[0]),
        222_638.98158654713,
        rel_tol=0.0,
        abs_tol=ABS_TOLERANCE_M,
    )
    assert result.distances_m[1] == (0.0,)
    assert isclose(
        result.distances_m[2][0],
        222_638.98158654713,
        rel_tol=0.0,
        abs_tol=ABS_TOLERANCE_M,
    )
    assert serialize_gpx(source) == original
    assert validate_spatial(source) == result


def test_forward_reverse_path_preserves_segment_length():
    """Reversing one path changes edge order, not total ellipsoidal length."""
    vertices = [(12.0, -86.0), (12.1, -85.9), (12.2, -86.1)]
    def route(points):
        return _document(
            "<rte>" + "".join(
                f'<rtept lat="{latitude}" lon="{longitude}"/>'
                for latitude, longitude in points
            ) + "</rte>"
        )
    forward = validate_spatial(route(vertices))
    backward = validate_spatial(route(list(reversed(vertices))))
    assert forward.valid and backward.valid
    assert isclose(
        fsum(forward.distances_m[0]),
        fsum(backward.distances_m[0]),
        rel_tol=1e-14,
        abs_tol=1e-9,
    )
    assert forward.distances_m[0] == tuple(reversed(backward.distances_m[0]))
