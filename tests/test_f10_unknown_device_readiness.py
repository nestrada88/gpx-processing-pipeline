"""Regression coverage for F10's unrecognized Garmin profile fallback."""

from dataclasses import replace

from gpx_pipeline import parse_gpx
from gpx_pipeline.garmin_export import (
    GarminDeviceProfile, export_garmin_navigation,
)
from gpx_pipeline.operational_verification import verify_device_readiness


def test_unknown_device_profile_fails_closed_without_physical_claims():
    """An unexpected profile reports an error, never inferred compatibility."""
    namespace = "http://www.topografix.com/GPX/1/1"
    source = parse_gpx(
        (f'<gpx xmlns="{namespace}" version="1.1" creator="test">'
         '<trk><trkseg><trkpt lat="12" lon="-86"/>'
         '<trkpt lat="12.001" lon="-86.001"/>'
         '</trkseg></trk></gpx>').encode(),
        strict=False,
    )
    valid_export = export_garmin_navigation(source)
    unexpected = replace(
        valid_export,
        profile=GarminDeviceProfile(
            "unknown-garmin", "Unsupported test device",
            "unrecognized transfer", None,
        ),
    )
    outcome = verify_device_readiness(source, unexpected)
    assert outcome.device_id == "unknown-garmin"
    assert outcome.software_compatible is False
    assert outcome.physical_transfer_verified is False
    assert outcome.physical_navigation_verified is False
    assert [(item.code, item.severity) for item in outcome.findings] == [
        ("UNKNOWN_DEVICE", "error"),
        ("FIELD_DEVICE_TEST_UNVERIFIED", "unverified"),
    ]
