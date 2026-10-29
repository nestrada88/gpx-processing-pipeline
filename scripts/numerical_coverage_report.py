"""Summarize pytest-cov JSON evidence without asserting numerical correctness.

Usage: python scripts/numerical_coverage_report.py coverage.json
Produces stable JSON with measured totals and a domain-focused source inventory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


NUMERICAL_MODULES = (
    "spatial.py",
    "dem.py",
    "dem_sampling_adapter.py",
    "terrain.py",
    "terrain_sampling.py",
    "temporal.py",
    "analytical.py",
    "route_analysis.py",
    "activity_forecasting.py",
    "planned_recorded.py",
    "pipeline.py",
)


def summarize(report: dict) -> dict:
    """Extract measured totals and numerical-module evidence from coverage JSON."""
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise ValueError("Expected pytest-cov JSON with a files dictionary")
    totals = report.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("Expected pytest-cov totals")
    files = report["files"]
    modules = {}
    missing = []
    for name in NUMERICAL_MODULES:
        matches = [
            (path, data) for path, data in files.items()
            if path.replace("\\", "/").endswith("/" + name)
            or path == name
        ]
        if len(matches) != 1:
            missing.append(name)
            continue
        path, data = matches[0]
        summary = data.get("summary", {})
        modules[name] = {
            "path": path,
            "covered_lines": summary.get("covered_lines"),
            "num_statements": summary.get("num_statements"),
            "percent_covered": summary.get("percent_covered"),
            "covered_branches": summary.get("covered_branches"),
            "num_branches": summary.get("num_branches"),
            "missing_lines": data.get("missing_lines", []),
            "missing_branches": data.get("missing_branches", []),
        }
    return {
        "format": "nv06-coverage-evidence-v1",
        "totals": {
            key: totals.get(key)
            for key in (
                "covered_lines", "num_statements", "percent_covered",
                "covered_branches", "num_branches",
            )
        },
        "modules": modules,
        "missing_modules": missing,
        "note": (
            "Execution coverage is not independent numerical accuracy, "
            "DEM quality, or physical Garmin device verification."
        ),
    }


def main() -> int:
    """Read coverage JSON and write a deterministic machine-readable summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Write evidence to a file instead of stdout",
    )
    args = parser.parse_args()
    summary = summarize(json.loads(args.coverage_json.read_text(encoding="utf-8")))
    encoded = json.dumps(
        summary, sort_keys=True, indent=2, allow_nan=False
    ) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
