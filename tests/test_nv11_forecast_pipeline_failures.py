"""NV-11 forecast and pipeline error-path regression contracts."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import inf, nan

import pytest

from gpx_pipeline import parse_gpx, serialize_gpx
from gpx_pipeline.activity_forecasting import (
    ForecastError, ForecastOptions, forecast_activity, tobler_speed_kmh,
)
from gpx_pipeline.analytical import build_analytical_dataset
from gpx_pipeline.pipeline import PipelineError, run_pipeline
from gpx_pipeline.pipeline_config import PipelineConfig


NS = "http://www.topografix.com/GPX/1/1"


def _xml(*timestamps):
    """Build a valid GPX track with explicit recorded clock observations."""
    points = "".join(
        f'<trkpt lat="0" lon="{index * .001}">'
        f"<time>{timestamp}</time></trkpt>"
        for index, timestamp in enumerate(timestamps)
    )
    return (
        f'<gpx xmlns="{NS}" version="1.1" creator="nv11">'
        f"<trk><trkseg>{points}</trkseg></trk></gpx>"
    ).encode()


def _dataset():
    """Produce valid source geometry with no assumed DEM or source elevation."""
    document = parse_gpx(
        _xml("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"),
        strict=False,
    )
    return document, build_analytical_dataset(document, include_temporal=False)


@pytest.mark.parametrize(
    ("grade", "minimum", "maximum"),
    [
        (nan, .3, 8),
        (inf, .3, 8),
        (0, nan, 8),
        (0, .3, inf),
        (0, 0, 8),
        (0, 8, 7),
    ],
)
def test_tobler_rejects_nonfinite_or_unordered_model_parameters(
    grade, minimum, maximum,
):
    """Invalid model inputs cannot return a plausible-looking walking speed."""
    with pytest.raises(ValueError):
        tobler_speed_kmh(
            grade, min_speed_kmh=minimum, max_speed_kmh=maximum
        )


def test_tobler_speed_clamps_are_explicit():
    """Configured physically bounded model speed must respect both limits."""
    assert tobler_speed_kmh(-5, min_speed_kmh=.3, max_speed_kmh=4) == 4
    assert tobler_speed_kmh(1000, min_speed_kmh=.5, max_speed_kmh=8) == .5


def test_finish_datetime_overflow_is_a_typed_forecast_error():
    """Out-of-range ETA must never silently wrap to an inaccurate timestamp."""
    document, dataset = _dataset()
    original = serialize_gpx(document)
    with pytest.raises(ForecastError, match="datetime range"):
        forecast_activity(
            dataset, options=ForecastOptions(
                missing_grade="assume", assumed_grade_percent=0,
                start_time=datetime.max.replace(tzinfo=timezone.utc),
                rest_seconds=3600,
            ),
        )
    assert serialize_gpx(document) == original


@pytest.mark.parametrize(
    "bad_time",
    [
        "2026-01-01T00:00:00Z",
        "2025-12-31T23:59:00Z",
    ],
)
def test_pipeline_blocks_invalid_chronology_without_output(tmp_path, bad_time):
    """Duplicate or decreasing timestamps never generate published analytics."""
    source = tmp_path / "chronology.gpx"
    source.write_bytes(
        _xml("2026-01-01T00:00:00Z", bad_time)
    )
    original = source.read_bytes()
    destination = tmp_path / "analytics"
    with pytest.raises(PipelineError, match="F04 temporal validation failed") as error:
        run_pipeline(PipelineConfig(
            command="analyze", input_path=source, output_dir=destination,
        ))
    assert error.value.code == "TEMPORAL_INVALID"
    assert not destination.exists()
    assert source.read_bytes() == original


def test_no_dem_requires_explicit_grade_assumption_for_forecast():
    """Forecast remains unavailable without a DEM or an explicit assumption."""
    _, dataset = _dataset()
    output = forecast_activity(dataset)
    assert output.scenarios[1].moving_s is None
    assert output.scenarios[1].finish_time is None
    assert "INCOMPLETE_FORECAST" in output.diagnostics
    assert "ASSUMED_GRADE_USED" not in output.diagnostics
