"""NV-16 canonical analytical assembly rejects corrupted upstream contracts."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from gpx_pipeline import parse_gpx
from gpx_pipeline.analytical import (
    AnalyticalDatasetError, build_analytical_dataset,
)
from gpx_pipeline.waypoints import enrich_waypoints

NS = "http://www.topografix.com/GPX/1/1"


def _source(*, waypoint=False):
    """Create immutable, valid GPX 1.1 geometry with optional waypoint."""
    wpt = '<wpt lat="0" lon="0"><name>Start</name></wpt>' if waypoint else ""
    return parse_gpx(
        (f'<gpx xmlns="{NS}" version="1.1" creator="nv16">'
         f'{wpt}<trk><trkseg>'
         '<trkpt lat="0" lon="0"/>'
         '<trkpt lat="0" lon="0.001"/>'
         '</trkseg></trk></gpx>').encode(),
        strict=False,
    )


def test_dataset_rejects_negative_f02_validation_result(monkeypatch):
    """A negative upstream spatial verdict cannot create canonical rows."""
    import gpx_pipeline.analytical as analytical

    monkeypatch.setattr(
        analytical, "validate_spatial",
        lambda _doc: SimpleNamespace(valid=False, distances_m=()),
    )
    with pytest.raises(AnalyticalDatasetError, match="F02 spatial validation failed"):
        build_analytical_dataset(_source(), include_temporal=False)


@pytest.mark.parametrize(
    ("distances", "message"),
    [
        ((), "Spatial segment count mismatch"),
        (((),), "Spatial edge count mismatch"),
    ],
)
def test_dataset_rejects_corrupted_f02_distance_shapes(
    monkeypatch, distances, message,
):
    """Never zip/truncate mismatched upstream segment and edge arrays."""
    import gpx_pipeline.analytical as analytical

    monkeypatch.setattr(
        analytical, "validate_spatial",
        lambda _doc: SimpleNamespace(valid=True, distances_m=distances),
    )
    with pytest.raises(AnalyticalDatasetError, match=message):
        build_analytical_dataset(_source(), include_temporal=False)


def test_dataset_rejects_incomplete_waypoint_catalog():
    """An omitted waypoint catalog entry is not an acceptable partial join."""
    document = _source(waypoint=True)
    catalog = enrich_waypoints(document)
    shortened = replace(catalog, entries=())
    with pytest.raises(AnalyticalDatasetError, match="Waypoint catalog count mismatch"):
        build_analytical_dataset(
            document, waypoints=shortened, include_temporal=False,
        )


def test_dataset_rejects_waypoint_source_identity_mismatch():
    """A catalog coordinate mismatch cannot rewrite source-linked positions."""
    document = _source(waypoint=True)
    catalog = enrich_waypoints(document)
    alien = replace(catalog.entries[0], longitude=1.0)
    altered = replace(catalog, entries=(alien,))
    with pytest.raises(AnalyticalDatasetError, match="Waypoint catalog source mismatch"):
        build_analytical_dataset(
            document, waypoints=altered, include_temporal=False,
        )
