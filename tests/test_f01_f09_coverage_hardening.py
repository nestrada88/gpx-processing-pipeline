"""Target missed F01/F09 validation and safe-publication branches.

These tests exercise existing failure contracts; no runtime mutation is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gpx_pipeline import (
    GPXLimits,
    GPXSchemaError,
    SchemaRegistry,
    parse_gpx,
)
from gpx_pipeline.output import OutputError, publish_outputs
from gpx_pipeline.pipeline_config import PipelineConfig


GPX = (
    b'<gpx xmlns="http://www.topografix.com/GPX/1/1" '
    b'version="1.1" creator="coverage"/>'
)


@pytest.mark.parametrize("field", ["max_bytes", "max_nodes", "max_depth"])
@pytest.mark.parametrize("invalid", [0, -1])
def test_f01_rejects_nonpositive_resource_limit(field: str, invalid: int) -> None:
    """Do not admit nonpositive XML resource ceilings."""
    with pytest.raises(ValueError, match="positive"):
        GPXLimits(**{field: invalid})


@pytest.mark.parametrize(
    "schema_bytes",
    [
        b"<xs:schema",
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        b'<xs:element name="gpx" type="xs:unknownType"/>'
        b"</xs:schema>",
    ],
)
def test_f01_rejects_malformed_or_uncompilable_local_xsd(
    tmp_path: Path, schema_bytes: bytes,
) -> None:
    """Reject broken local XSD instead of accepting GPX without verification."""
    schema = tmp_path / "broken.xsd"
    schema.write_bytes(schema_bytes)
    with pytest.raises(GPXSchemaError, match="Cannot load XSD"):
        parse_gpx(GPX, registry=SchemaRegistry(gpx11_xsd=schema))


def test_f01_rejects_unreadable_schema_path(tmp_path: Path) -> None:
    """Missing schema files do not silently disable strict validation."""
    with pytest.raises(GPXSchemaError, match="Cannot load XSD"):
        parse_gpx(
            GPX,
            registry=SchemaRegistry(gpx11_xsd=tmp_path / "absent.xsd"),
        )


def test_f01_rejects_xsd_invalid_document(tmp_path: Path) -> None:
    """A compilable XSD rejection must propagate as a GPX schema error."""
    schema = tmp_path / "require-special-root.xsd"
    schema.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'targetNamespace="http://www.topografix.com/GPX/1/1" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        'elementFormDefault="qualified">'
        '<xs:element name="gpx"><xs:complexType><xs:sequence>'
        '<xs:element name="requiredChild" type="xs:string"/>'
        '</xs:sequence></xs:complexType></xs:element></xs:schema>',
        encoding="utf-8",
    )
    with pytest.raises(GPXSchemaError, match="GPX 1.1 XSD"):
        parse_gpx(GPX, registry=SchemaRegistry(gpx11_xsd=schema))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"command": "unsupported"}, "Unsupported pipeline command"),
        ({"max_input_bytes": 0}, "max_input_bytes must be positive"),
        ({"input_path": None}, "Input GPX path required"),
        ({"output_dir": None}, "output directory is required"),
        ({"adaptive_sampling": True}, "Adaptive sampling requires a DEM"),
        ({"dem_path": Path("dem.tif"), "command": "validate"},
         "DEM only applies"),
        ({"adaptive_sampling": True, "dem_path": Path("dem.tif"),
          "command": "export", "garmin_devices": ("etrex-se",)},
         "Adaptive sampling only applies"),
        ({"forecast": True, "command": "validate"}, "Forecast only applies"),
        ({"garmin_devices": ("etrex-se",), "command": "analyze"},
         "Garmin targets only apply"),
        ({"garmin_devices": ("invalid-model",), "command": "process"},
         "Unsupported Garmin target"),
        ({"command": "export"}, "export requires at least one Garmin target"),
        ({"assume_flat_grade": True}, "Flat-grade assumption requires forecasting"),
        ({"command": "compare", "planned_path": None},
         "compare requires planned and recorded"),
    ],
)
def test_f09_rejects_invalid_configuration_branches(
    changes: dict[str, object], message: str,
) -> None:
    """Each documented contradictory operation fails before file access."""
    values: dict[str, object] = {
        "command": "analyze",
        "input_path": Path("input.gpx"),
        "output_dir": Path("out"),
        "planned_path": Path("planned.gpx"),
        "recorded_path": Path("recorded.gpx"),
    }
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        PipelineConfig(**values)


@pytest.mark.parametrize(
    ("artifacts", "message"),
    [
        ({}, "No outputs to publish"),
        ({"manifest.json": b"duplicate"}, "Invalid output path"),
        ({"/absolute": b"bad"}, "Invalid output path"),
        ({"nested/../../escape": b"bad"}, "Invalid output path"),
        ({"data.bin": "not bytes"}, "payloads must be bytes"),
    ],
)
def test_f09_rejects_unsafe_output_before_creating_destination(
    tmp_path: Path, artifacts: dict, message: str,
) -> None:
    """Invalid payloads must not publish a destination or stage."""
    destination = tmp_path / "not-published"
    with pytest.raises(OutputError, match=message):
        publish_outputs(destination, artifacts, command="analyze", inputs={})
    assert not destination.exists()
    assert not list(tmp_path.glob(".gpx-stage-*"))


def test_f09_rejects_missing_output_parent(tmp_path: Path) -> None:
    """Publishing never invents missing parent directories."""
    destination = tmp_path / "missing-parent" / "result"
    with pytest.raises(OutputError, match="parent directory"):
        publish_outputs(
            destination, {"data.bin": b"ok"}, command="analyze", inputs={},
        )
    assert not destination.parent.exists()


def test_f09_blocks_existing_symlink_destination(tmp_path: Path) -> None:
    """Existing symlinks cannot become overwritten output directories."""
    original = tmp_path / "preserved"
    original.mkdir()
    destination = tmp_path / "linked"
    destination.symlink_to(original, target_is_directory=True)
    with pytest.raises(OutputError, match="already exists"):
        publish_outputs(
            destination, {"data.bin": b"ok"}, command="analyze", inputs={},
        )
    assert destination.is_symlink()
    assert list(original.iterdir()) == []


def test_f09_rolls_back_when_destination_appears_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A racing output destination prevents replacement and clears staging."""
    import gpx_pipeline.output as output_module

    destination = tmp_path / "result"
    original_fsync = output_module.os.fsync
    already_created = False

    def competing_writer(fd: int) -> None:
        nonlocal already_created
        if not already_created:
            destination.mkdir()
            (destination / "sentinel").write_text("keep", encoding="utf-8")
            already_created = True
        original_fsync(fd)

    monkeypatch.setattr(output_module.os, "fsync", competing_writer)
    with pytest.raises(OutputError, match="appeared during staging"):
        publish_outputs(
            destination, {"data.bin": b"ok"}, command="analyze", inputs={},
        )
    assert (destination / "sentinel").read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".gpx-stage-*"))
