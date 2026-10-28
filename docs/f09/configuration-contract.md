# F09 — Configuration Contract

[← F09 overview](../F09-PIPELINE-ORCHESTRATION-CLI.md)

Implementation: [`src/gpx_pipeline/pipeline_config.py`](../../src/gpx_pipeline/pipeline_config.py). `PipelineConfig` is an immutable `@dataclass(frozen=True, slots=True)`; contradictory settings are rejected in `__post_init__` before reading files.

## Fields and defaults

| Field | Python type / default | Intended use |
| --- | --- | --- |
| `command` | Literal among `validate`, `process`, `analyze`, `export`, `compare`; required | Execution mode |
| `input_path` | `Path | None = None` | Source GPX except for comparison |
| `output_dir` | `Path | None = None` | New destination except validation |
| `dem_path` | `Path | None = None` | Local DEM for process/analyze |
| `planned_path` | `Path | None = None` | Planned GPX for compare |
| `recorded_path` | `Path | None = None` | Recorded GPX for compare |
| `adaptive_sampling` | `bool = False` | Request DEM-backed adaptive sampling |
| `forecast` | `bool = False` | Request F06 simulated travel times |
| `garmin_devices` | `tuple[str, ...] = ()` | Explicit independent device exports |
| `assume_flat_grade` | `bool = False` | Opt into assumed 0% grade where absent |
| `max_input_bytes` | `int = 8_000_000` | Per-GPX input byte ceiling |

## Validity matrix

- `compare` requires **both** `planned_path` and `recorded_path`. All other commands require `input_path`.
- `validate` requires no `output_dir`; other commands require it. `PipelineConfig` does not forbid supplying an ignored output path for `validate`, but the CLI does not expose that flag.
- `dem_path`, `adaptive_sampling`, and `forecast` only apply to `process`/`analyze`.
- `adaptive_sampling=True` requires `dem_path`.
- `assume_flat_grade=True` requires `forecast=True`; it does not itself verify that the terrain is flat.
- Nonempty `garmin_devices` is only valid for `process`/`export`. `export` requires at least one target.
- The only device IDs are `etrex-se` and `instinct-2x-tactical`. Repeated target IDs in one config are rejected; multiple distinct targets are allowed.
- `max_input_bytes` must be positive. Actual local GPX file length is tested later by `_read_document`.

These are the concrete checks in `__post_init__`. Do not imply validation of every field's runtime Python type beyond the explicit checks; malformed direct Python configuration may raise native type errors.

## Direct Python usage

```python
from pathlib import Path
from gpx_pipeline.pipeline_config import PipelineConfig
from gpx_pipeline.pipeline import run_pipeline

config = PipelineConfig(
    command="analyze",
    input_path=Path("route.gpx"),
    output_dir=Path("results/analysis-01"),
    forecast=True,
    assume_flat_grade=False,
)
result = run_pipeline(config)
print(result.command, result.output_dir, result.artifacts)
```

The GPX must exist and be valid; the output parent must exist while `results/analysis-01` must **not** already exist. The function does not create an output parent automatically. For file/manifest semantics see [output publication](output-publication.md).

## Error handling

`PipelineConfig` throws `ValueError` for detected contradictions. The CLI converts these to stderr `CONFIG_INVALID: ...` and exit 2. Direct Python callers must handle them independently.

This document describes current application constraints, not a generic configuration-file schema or an interactive settings loader. No YAML/TOML input configuration, persistent user profiles or automatic device discovery is implemented in this module.
