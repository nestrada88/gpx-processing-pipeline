"""Typed configuration for the offline, single-run GPX application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Select deterministic outputs and bounded input handling."""

    command: Literal["validate", "process", "analyze", "export", "compare"]
    input_path: Path | None = None
    output_dir: Path | None = None
    dem_path: Path | None = None
    planned_path: Path | None = None
    recorded_path: Path | None = None
    adaptive_sampling: bool = False
    forecast: bool = False
    garmin_devices: tuple[str, ...] = ()
    assume_flat_grade: bool = False
    max_input_bytes: int = 8_000_000

    def __post_init__(self) -> None:
        """Reject contradictory operations before reading inputs."""
        if self.command not in {"validate", "process", "analyze", "export", "compare"}:
            raise ValueError("Unsupported pipeline command")
        if self.max_input_bytes < 1:
            raise ValueError("max_input_bytes must be positive")
        if self.command == "compare":
            if self.planned_path is None or self.recorded_path is None:
                raise ValueError("compare requires planned and recorded files")
        elif self.input_path is None:
            raise ValueError("Input GPX path required")
        if self.command != "validate" and self.output_dir is None:
            raise ValueError("An output directory is required")
        if self.adaptive_sampling and self.dem_path is None:
            raise ValueError("Adaptive sampling requires a DEM")
        if self.dem_path is not None and self.command not in {"process", "analyze"}:
            raise ValueError("DEM only applies to process/analyze")
        if self.adaptive_sampling and self.command not in {"process", "analyze"}:
            raise ValueError("Adaptive sampling only applies to process/analyze")
        if self.forecast and self.command not in {"process", "analyze"}:
            raise ValueError("Forecast only applies to process/analyze")
        if self.garmin_devices and self.command not in {"process", "export"}:
            raise ValueError("Garmin targets only apply to process/export")
        if any(device not in {"etrex-se", "instinct-2x-tactical"}
               for device in self.garmin_devices):
            raise ValueError("Unsupported Garmin target")
        if len(set(self.garmin_devices)) != len(self.garmin_devices):
            raise ValueError("Duplicate Garmin target")
        if self.command == "export" and not self.garmin_devices:
            raise ValueError("export requires at least one Garmin target")
        if self.assume_flat_grade and not self.forecast:
            raise ValueError("Flat-grade assumption requires forecasting")
