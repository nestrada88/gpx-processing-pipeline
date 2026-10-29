"""NV-15 publication atomicity across pipeline input and validation failures."""

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from gpx_pipeline.pipeline import PipelineError, run_pipeline
from gpx_pipeline.pipeline_config import PipelineConfig


NS = "http://www.topografix.com/GPX/1/1"


def _source(tmp_path):
    """Produce a valid minimal GPX input without disk output side effects."""
    source = tmp_path / "source.gpx"
    source.write_text(
        f'<gpx xmlns="{NS}" version="1.1" creator="nv15">'
        '<trk><trkseg><trkpt lat="0" lon="0"/>'
        '<trkpt lat="0" lon="0.001"/></trkseg></trk></gpx>',
        encoding="utf-8",
    )
    return source


def test_unreadable_existing_gpx_is_typed_input_failure(tmp_path, monkeypatch):
    """Failure to read the original GPX must not publish partial analytics."""
    source = _source(tmp_path)
    before = sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "out"
    original_read_bytes = Path.read_bytes

    def fail_source_only(path):
        if path == source:
            raise OSError("injected read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_source_only)
    with pytest.raises(PipelineError, match="injected read failure") as captured:
        run_pipeline(PipelineConfig(
            command="analyze", input_path=source, output_dir=output,
        ))
    assert captured.value.code == "INPUT_UNAVAILABLE"
    assert not output.exists()
    assert sha256(original_read_bytes(source)).hexdigest() == before


def test_upstream_spatial_failure_blocks_analytical_publication(
    tmp_path, monkeypatch,
):
    """Even schema-valid GPX may not bypass a negative spatial verdict."""
    import gpx_pipeline.pipeline as pipeline

    source = _source(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr(
        pipeline, "validate_spatial",
        lambda _document: SimpleNamespace(valid=False),
    )
    with pytest.raises(PipelineError, match="F02 spatial validation failed") as caught:
        run_pipeline(PipelineConfig(
            command="analyze", input_path=source, output_dir=output,
        ))
    assert caught.value.code == "SPATIAL_INVALID"
    assert not output.exists()


def test_dem_fingerprint_io_failure_blocks_publication(tmp_path, monkeypatch):
    """A DEM hash read error must not leave a misleading analytics product."""
    import gpx_pipeline.pipeline as pipeline
    from gpx_pipeline.analytical import build_analytical_dataset

    source = _source(tmp_path)
    output = tmp_path / "out"

    def no_raster_dataset(document, _dem_path=None):
        return build_analytical_dataset(document, include_temporal=False)

    def fail_hash(_path):
        raise OSError("injected DEM fingerprint failure")

    monkeypatch.setattr(pipeline, "_dataset", no_raster_dataset)
    monkeypatch.setattr(pipeline, "_hash_local_file", fail_hash)
    with pytest.raises(
        PipelineError, match="injected DEM fingerprint failure"
    ) as caught:
        run_pipeline(PipelineConfig(
            command="analyze", input_path=source,
            output_dir=output, dem_path=tmp_path / "dem.tif",
        ))
    assert caught.value.code == "INPUT_UNAVAILABLE"
    assert not output.exists()
