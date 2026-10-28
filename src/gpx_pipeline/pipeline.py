"""F09 sequential GPX validation, analytics, comparison and Garmin export."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .activity_forecasting import (
    ForecastOptions, activity_forecast_json, forecast_activity,
)
from .analytical import analytical_json, build_analytical_dataset
from .dem import enrich_dem
from .dem_sampling_adapter import dem_sampling_json, sample_terrain_from_dem
from .garmin_compatibility import (
    GarminCompatibilityOptions, garmin_verification_json,
)
from .garmin_export import NavigationExportOptions, export_garmin_navigation
from .interoperability import GPXLimits, parse_gpx
from .output import publish_outputs
from .pipeline_config import PipelineConfig
from .planned_recorded import compare_planned_recorded, planned_recorded_json
from .production_schemas import (
    validate_production_gpx, verify_production_garmin_export,
)
from .route_analysis import analyze_route, route_analysis_json
from .spatial import validate_spatial
from .temporal import analyze_temporal
from .waypoints import enrich_waypoints


class PipelineError(ValueError):
    """Report a failed mandatory processing stage with a stable category."""

    def __init__(self, code: str, message: str):
        """Retain stable diagnostic code and human-readable reason."""
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Identify a completed run and all published artifact paths."""

    command: str
    output_dir: Path | None
    artifacts: tuple[str, ...]
    input_sha256: tuple[tuple[str, str], ...]


def _read_document(path: Path, limit: int):
    """Read a bounded local source and require true GPX 1.1 compliance."""
    try:
        if not path.is_file():
            raise PipelineError("INPUT_UNAVAILABLE", f"GPX file not found: {path}")
        if path.stat().st_size > limit:
            raise PipelineError("INPUT_LIMIT", "GPX file exceeds byte limit")
        source = path.read_bytes()
    except OSError as exc:
        raise PipelineError("INPUT_UNAVAILABLE", str(exc)) from exc
    try:
        document = parse_gpx(
            source, strict=False, limits=GPXLimits(max_bytes=limit)
        )
        validate_production_gpx(
            document, limits=GPXLimits(max_bytes=limit)
        )
        if not validate_spatial(document).valid:
            raise PipelineError("SPATIAL_INVALID", "F02 spatial validation failed")
        result = analyze_temporal(document)
        # Temporal findings are classified by F04; do not recast warnings as
        # invalid unless explicitly marked as errors.
        if any(getattr(f, "severity", None) == "error"
               for f in result.findings):
            raise PipelineError("TEMPORAL_INVALID", "F04 temporal validation failed")
    except PipelineError:
        raise
    except (ValueError, TypeError) as exc:
        raise PipelineError("GPX_INVALID", str(exc)) from exc
    return document


def _dataset(document, dem_path=None):
    """Assemble immutable source data and optional raster-derived DEM values."""
    catalog = enrich_waypoints(document)
    dem = enrich_dem(document, dem_path) if dem_path is not None else None
    return build_analytical_dataset(document, dem=dem, waypoints=catalog)


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Execute ordered operations, publishing only after every stage succeeds."""
    artifacts: dict[str, bytes] = {}
    inputs: dict[str, str] = {}
    if config.command == "compare":
        planned = _read_document(config.planned_path, config.max_input_bytes)
        recorded = _read_document(config.recorded_path, config.max_input_bytes)
        inputs["planned"] = sha256(planned.xml).hexdigest()
        inputs["recorded"] = sha256(recorded.xml).hexdigest()
        left = _dataset(planned)
        right = _dataset(recorded)
        artifacts["comparison/planned-vs-recorded.json"] = planned_recorded_json(
            compare_planned_recorded(left, right)
        )
    else:
        document = _read_document(config.input_path, config.max_input_bytes)
        inputs["source"] = sha256(document.xml).hexdigest()
        if config.command == "validate":
            return PipelineResult(
                "validate", None, (), tuple(sorted(inputs.items()))
            )
        if config.command in {"analyze", "process"}:
            dataset = _dataset(document, config.dem_path)
            if config.dem_path is not None:
                try:
                    inputs["dem"] = sha256(config.dem_path.read_bytes()).hexdigest()
                except OSError as exc:
                    raise PipelineError("INPUT_UNAVAILABLE", str(exc)) from exc
            artifacts["analytical/dataset.json"] = analytical_json(dataset)
            artifacts["analytical/route-analysis.json"] = route_analysis_json(
                analyze_route(dataset)
            )
            if config.adaptive_sampling:
                artifacts["analytical/terrain-sampling.json"] = dem_sampling_json(
                    sample_terrain_from_dem(dataset, config.dem_path)
                )
            if config.forecast:
                settings = ForecastOptions(
                    missing_grade=(
                        "assume" if config.assume_flat_grade else "unavailable"
                    ),
                )
                artifacts["analytical/activity-forecast.json"] = activity_forecast_json(
                    forecast_activity(dataset, options=settings)
                )
        if config.command in {"process", "export"}:
            for device in config.garmin_devices:
                export = export_garmin_navigation(
                    document, options=NavigationExportOptions(device_id=device)
                )
                workflow = (
                    "explore-web-tracks" if device == "etrex-se"
                    else "connect-course"
                )
                verified = verify_production_garmin_export(
                    document, export,
                    options=GarminCompatibilityOptions(
                        workflow=workflow, require_xsd=True,
                    ),
                )
                if verified.software_status == "incompatible":
                    raise PipelineError(
                        "GARMIN_INCOMPATIBLE",
                        f"{device}: Garmin export verification failed: "
                        + ", ".join(f.code for f in verified.findings
                                    if f.severity == "error"),
                    )
                artifacts[f"navigation/{device}.gpx"] = export.gpx
                artifacts[f"navigation/{device}-manifest.json"] = export.manifest()
                artifacts[f"verification/{device}.json"] = garmin_verification_json(
                    verified
                )
    if not artifacts:
        raise PipelineError("NO_OUTPUT", "No output operations were selected")
    try:
        paths = publish_outputs(
            config.output_dir, artifacts, command=config.command, inputs=inputs
        )
    except OSError as exc:
        raise PipelineError("OUTPUT_FAILED", str(exc)) from exc
    return PipelineResult(
        config.command, config.output_dir, paths, tuple(sorted(inputs.items()))
    )
