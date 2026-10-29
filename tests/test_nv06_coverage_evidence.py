"""NV-06 regression coverage evidence tool contracts."""

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "numerical_coverage_report.py"
_SPEC = importlib.util.spec_from_file_location("numerical_coverage_report", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_coverage_summary_preserves_measured_values_without_invention():
    """Read real-shaped input without fabricating coverage for absent modules."""
    fixture = {
        "totals": {
            "covered_lines": 90, "num_statements": 100,
            "percent_covered": 90.0, "covered_branches": 8,
            "num_branches": 10,
        },
        "files": {
            "src/gpx_pipeline/spatial.py": {
                "summary": {
                    "covered_lines": 9, "num_statements": 10,
                    "percent_covered": 90.0, "covered_branches": 4,
                    "num_branches": 5,
                },
                "missing_lines": [17],
                "missing_branches": [[12, 17]],
            },
        },
    }
    result = _MODULE.summarize(fixture)
    assert result["totals"]["percent_covered"] == 90.0
    spatial = result["modules"]["spatial.py"]
    assert spatial["missing_lines"] == [17]
    assert spatial["missing_branches"] == [[12, 17]]
    assert spatial["covered_branches"] == 4
    assert "dem.py" in result["missing_modules"]
    assert result["format"] == "nv06-coverage-evidence-v1"


@pytest.mark.parametrize("bad", [{}, {"files": []}, {"files": {}}, []])
def test_coverage_summary_rejects_incomplete_or_invalid_input(bad):
    """Missing coverage metadata must never be interpreted as zero coverage."""
    with pytest.raises(ValueError):
        _MODULE.summarize(bad)


def test_numerical_module_inventory_is_unambiguous():
    """Every target numerical component appears exactly once."""
    modules = _MODULE.NUMERICAL_MODULES
    assert len(modules) == len(set(modules))
    assert {
        "spatial.py", "dem.py", "terrain.py", "temporal.py",
        "analytical.py", "route_analysis.py",
        "activity_forecasting.py", "pipeline.py",
    }.issubset(modules)
