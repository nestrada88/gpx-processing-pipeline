"""F09 installed command-line interface for offline GPX processing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .pipeline import PipelineError, run_pipeline
from .pipeline_config import PipelineConfig


def _parser() -> argparse.ArgumentParser:
    """Define a discoverable, conventional subcommand interface."""
    parser = argparse.ArgumentParser(
        prog="gpx-pipeline",
        description="Offline GPX validation, terrain analysis, and Garmin export.",
    )
    parser.add_argument("--debug", action="store_true", help="Show exception details")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "process", "analyze", "export", "compare"):
        command = commands.add_parser(name)
        if name == "compare":
            command.add_argument("--planned", type=Path, required=True)
            command.add_argument("--recorded", type=Path, required=True)
        else:
            command.add_argument("input", type=Path)
        if name != "validate":
            command.add_argument("--output", type=Path, required=True)
        if name in {"process", "analyze"}:
            command.add_argument("--dem", type=Path)
            command.add_argument("--adaptive-sampling", action="store_true")
            command.add_argument("--forecast", action="store_true")
            command.add_argument(
                "--assume-flat-grade", action="store_true",
                help="Explicitly assume zero grade where DEM is unavailable",
            )
        if name in {"process", "export"}:
            command.add_argument(
                "--garmin", action="append", default=[],
                choices=("etrex-se", "instinct-2x-tactical"),
                help="Repeat for independent Garmin device outputs",
            )
        if name == "validate":
            command.add_argument("--format", choices=("text", "json"), default="text")
        command.add_argument(
            "--max-input-bytes", type=int, default=8_000_000,
            help="Maximum bytes of each input GPX (default: 8000000)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one command and return a deterministic process exit status."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        config = PipelineConfig(
            command=arguments.command,
            input_path=getattr(arguments, "input", None),
            output_dir=getattr(arguments, "output", None),
            planned_path=getattr(arguments, "planned", None),
            recorded_path=getattr(arguments, "recorded", None),
            dem_path=getattr(arguments, "dem", None),
            adaptive_sampling=getattr(arguments, "adaptive_sampling", False),
            forecast=getattr(arguments, "forecast", False),
            assume_flat_grade=getattr(arguments, "assume_flat_grade", False),
            garmin_devices=tuple(getattr(arguments, "garmin", ())),
            max_input_bytes=arguments.max_input_bytes,
        )
    except (TypeError, ValueError) as exc:
        print(f"CONFIG_INVALID: {exc}", file=sys.stderr)
        return 2
    try:
        result = run_pipeline(config)
    except PipelineError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        if arguments.debug:
            raise
        if exc.code in {"GPX_INVALID", "SPATIAL_INVALID", "TEMPORAL_INVALID"}:
            return 3
        if exc.code in {"INPUT_UNAVAILABLE", "INPUT_LIMIT"}:
            return 4
        if exc.code == "GARMIN_INCOMPATIBLE":
            return 5
        if exc.code == "OUTPUT_FAILED":
            return 6
        return 1
    except Exception as exc:
        if arguments.debug:
            raise
        print(f"PROCESSING_FAILED: {exc}", file=sys.stderr)
        return 1
    if arguments.command == "validate":
        if arguments.format == "json":
            print(json.dumps({
                "valid": True,
                "sha256": dict(result.input_sha256)["source"],
            }, sort_keys=True, separators=(",", ":")))
        else:
            print("Valid GPX 1.1; spatial and temporal checks passed")
    else:
        print(str(result.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
