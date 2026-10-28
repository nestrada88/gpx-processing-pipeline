# F04 — Temporal and Kinematic Integrity

## Purpose and implementation evidence

F04 analyzes **recorded GPX track-point timestamps** and computes segment-scoped movement quantities from F02 geodesic edge distances. It never writes or synthesizes timestamps, edits GPX source geometry, or reconstructs missing measurements. This document describes the implementation in [`src/gpx_pipeline/temporal.py`](../src/gpx_pipeline/temporal.py), tested by [`tests/test_f04_temporal.py`](../tests/test_f04_temporal.py), and merged through [implementation PR #10](https://github.com/nestrada88/gpx-processing-pipeline/pull/10).

F01 provides a parsed `GPXDocument` and preserves source data. F02 validates coordinates and supplies ordered geodesic distances within each track/segment. F04 consumes these distances and observed timestamp text. F04 does **not** handle waypoint or route-point time series, planned-activity forecasts, sensor-provided moving time, Garmin device exports, or synthetic timing. See [F02 spatial integrity](F02-SPATIAL-INTEGRITY.md) for horizontal geometry semantics. Other downstream timing forecasts must not be presented as observed F04 measurements.

## Public interface

```python
from gpx_pipeline import (
    TemporalError,
    TemporalFinding,
    TemporalOptions,
    MovementEdge,
    TemporalSegment,
    TemporalResult,
    analyze_temporal,
)

result: TemporalResult = analyze_temporal(
    document: GPXDocument,
    *,
    options: TemporalOptions = TemporalOptions(),
)
```

The function annotation above is conceptual: its actual signature is `analyze_temporal(document: GPXDocument, *, options: TemporalOptions = TemporalOptions()) -> TemporalResult`. The input must pass `validate_spatial(document).valid`, otherwise `TemporalError("F02 spatial validation failed")` is raised.

### Configuration

`TemporalOptions` is an immutable dataclass with the following defaults:

| Field | Default | Units | Behavior |
| --- | ---: | --- | --- |
| `speed_warning_m_s` | `12.0` | m/s | Emit `SPEED_ANOMALY` when derived speed **exceeds** threshold. |
| `moving_speed_m_s` | `0.5` | m/s | Classify timed edge as moving when derived speed is **at least** threshold. |
| `gap_warning_s` | `1800.0` | s | Emit `TEMPORAL_GAP` when positive elapsed time **exceeds** threshold. |

All thresholds must be positive and finite, otherwise construction raises `ValueError`. These are configurable analytical thresholds rather than universal physiological limits; the speed-warning threshold does not clamp or correct values.

### Result objects

All listed result records are frozen dataclasses:

- `TemporalFinding(code, severity, track, segment, point)`: zero-based track, segment and point index; `point` identifies the timestamp or **ending** point of an anomalous edge.
- `MovementEdge(end_point, elapsed_s, distance_m, speed_m_s, pace_s_km, moving)`: one adjacent original track-point pair; an undefined time/speed/pace/movement field uses `None` rather than invented data.
- `TemporalSegment(track, segment, edges, elapsed_s, moving_s, timed_distance_m, moving_distance_m, average_speed_m_s, moving_speed_m_s, complete)`: per-track-segment aggregate, with no inter-segment connections.
- `TemporalResult(segments, findings)`: ordered segment results and diagnostic records. Its `valid` property is `True` precisely when **no finding has `severity == "error"`**. Validity is distinct from coverage/completeness.

There is one `MovementEdge` per adjacent trackpoint pair, so a segment containing `n` track points has `max(n-1, 0)` edges. Neither GPX standalone waypoints nor `rtept` entries produce F04 segments. Indexing is zero-based. Segment results preserve original track and segment order.

## Timestamp syntax and chronological interpretation

- A track point's direct GPX 1.1 `<time>` text must be a full ISO-8601-like datetime of the form `YYYY-MM-DDTHH:MM:SS[.fraction](Z|±HH:MM)` with an **explicit timezone offset**. The implementation uses a restrictive regular expression and `datetime.fromisoformat`.
- Valid offset-bearing timestamps are converted to timezone-aware UTC `datetime` values for subtraction. This normalizes equivalent instants expressed with different offsets.
- An absent `<time>` produces `MISSING_TIMESTAMP` (`warning`) at the point; there is no interpolation or inferred time.
- Present but malformed or invalid time text produces `INVALID_TIMESTAMP` (`error`), with that instant treated as unavailable for adjacent edges.
- Strictly increasing UTC instants are required for each *timed* adjacent edge. Equal timestamps produce `DUPLICATE_TIMESTAMP` (`error`); decreasing timestamps produce `REVERSED_TIMESTAMP` (`error`). Neither creates a defined velocity.
- Segments are independent: the end of one segment is never linked to the beginning of the next, and no chronology check is made across their boundary.

The timestamp regular expression and Python datetime parser determine accepted syntax and date ranges; F04 does not independently implement leap-second support or a comprehensive ISO 8601 parser. The original timestamp strings are not rewritten.

## Edge calculations and units

Let consecutive source points `i-1` and `i` in one track segment have valid UTC times `t[i-1]`, `t[i]` and F02 geodesic horizontal distance `d[i]` in meters.

- `elapsed_s = (t[i] - t[i-1]).total_seconds()`, only used for motion calculations when strictly greater than zero.
- `speed_m_s = d[i] / elapsed_s`, defined for positive elapsed duration.
- `pace_s_km = 1000 / speed_m_s` only when `speed_m_s > 0`. Stationary zero-distance edges have speed `0.0` and pace `None`.
- `moving = speed_m_s >= options.moving_speed_m_s` for valid positive-time edges only.

For a missing or invalid endpoint time, the output edge retains F02 `distance_m`, but `elapsed_s`, `speed_m_s`, `pace_s_km`, and `moving` are `None`, with an `UNKNOWN_EDGE_TIME` warning. For equal or reversed instants, `elapsed_s` preserves the measured zero/negative difference, but speed/pace/movement are `None`. Fatal chronology findings do not mutate the source.

No smoothing, gap bridging, displacement adjustment, stop interpolation, elevation-based speed correction or sensor-fusion is performed.

## Aggregate semantics and completeness

Only valid positive-time edges contribute to:

- `timed_distance_m = Σ d[i]`.
- `timed_seconds = Σ elapsed_s[i]` (internal accumulator).
- `moving_s = Σ elapsed_s[i]` over edges classified as moving.
- `moving_distance_m = Σ d[i]` over edges classified as moving.
- `average_speed_m_s = timed_distance_m / timed_seconds` if timed_seconds is positive; otherwise `None`.
- `moving_speed_m_s = moving_distance_m / moving_s` if moving_s is positive; otherwise `None`.

`complete` is true only when every trackpoint timestamp was parsed successfully and every expected adjacent edge has strictly positive elapsed time. `elapsed_s` for the segment equals the sum of timed edge durations **only when complete**; otherwise it is `None`. The accumulated moving-time and distance fields can be partial even when `complete=False`; never represent them as whole-segment totals in that case. A segment can have `result.valid=True` and `segment.complete=False` if it contains missing (but not malformed) timestamps.

A segment with zero points has no edges and, under the current rule, `complete=True`, `elapsed_s=0`, and no coverage metric. A single-point segment with a valid timestamp likewise has zero elapsed duration. This is a vacuous edge-completeness result, not evidence of recorded movement.

## Diagnostic catalog

| Code | Severity | Trigger | Effect |
| --- | --- | --- | --- |
| `MISSING_TIMESTAMP` | warning | Absent `<time>` element | Point time unknown; neighboring timed edges unavailable. |
| `INVALID_TIMESTAMP` | error | Present but malformed/invalid timestamp | Point time unknown; neighboring timed edges unavailable. |
| `UNKNOWN_EDGE_TIME` | warning | Either adjacent instant unavailable | Edge time, speed, pace and moving status undefined. |
| `DUPLICATE_TIMESTAMP` | error | Consecutive equal UTC instants | Elapsed edge 0; no speed. |
| `REVERSED_TIMESTAMP` | error | Consecutive decreasing UTC instants | Negative elapsed edge; no speed. |
| `SPEED_ANOMALY` | warning | Derived speed greater than configured warning threshold | Numerical result retained; not corrected. |
| `TEMPORAL_GAP` | warning | Positive edge elapsed exceeds configured gap threshold | Numerical result retained; not bridged. |

A failing F02 spatial validation or F02 edge-array inconsistency raises `TemporalError` rather than returning a `TemporalFinding`. `TemporalError` also covers invalid or nonfinite F02 distance arrays. Invalid `TemporalOptions` values instead raise `ValueError`.

## Executable usage example

The following self-contained example uses a source GPX 1.1 track with explicit timestamp offsets and standard F01 parsing:

```python
from gpx_pipeline import (
    TemporalOptions,
    analyze_temporal,
    parse_gpx,
)

source = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1"
     version="1.1" creator="f04-example">
  <trk><trkseg>
    <trkpt lat="0" lon="0"><time>2026-01-01T00:00:00Z</time></trkpt>
    <trkpt lat="0" lon="0.001"><time>2026-01-01T01:01:00+01:00</time></trkpt>
  </trkseg></trk>
</gpx>"""

document = parse_gpx(source, strict=False)
result = analyze_temporal(document, options=TemporalOptions())
segment = result.segments[0]
edge = segment.edges[0]

assert result.valid and segment.complete
assert edge.elapsed_s == 60.0
assert edge.speed_m_s is not None
print(edge.distance_m, edge.speed_m_s, edge.pace_s_km)
print(segment.elapsed_s, segment.moving_s, result.findings)
```

The two timestamps are 60 seconds apart after UTC normalization. F02 supplies the geodesic distance; F04 does not recalculate coordinates or alter timestamps. If using real recordings, inspect `result.valid`, each segment's `complete`, and `findings` before using aggregates operationally.

## Verification evidence and open limitations

Committed regression cases in `tests/test_f04_temporal.py` cover UTC offset normalization, geodesic speed/pace reference values, equal/reversed/malformed timestamps, warnings for missing samples, separation of independent segments, speed and gap thresholds, stationary versus moving classification, fractional seconds, empty/single-point segments, invalid threshold configuration and GPX serialization preservation. Implementation PR #10 is merged; neither that status nor the existence of tests proves a fresh successful test execution for this documentation change. Check CI run results or run `python -m pytest -q` in a configured checkout separately.

Limitations include: no synthesis of planned time, smoothing, advanced stop detection, cross-segment activity aggregation, sensor-specific motion signals, leap-second handling or inferred speeds through coverage gaps. Moving time is threshold-based and can differ from Garmin/device-reported moving time. Timestamp parsing requires explicit offsets; missing observations leave coverage gaps. The current implementation is a recorded-track foundation, **not proof of complete compliance with every historical temporal/kinematic requirement**.

## Traceability

- F04 implementation: `src/gpx_pipeline/temporal.py`
- F04 tests: `tests/test_f04_temporal.py`
- Source model: `src/gpx_pipeline/interoperability.py`
- Geodesic distance and validation: `src/gpx_pipeline/spatial.py`
- Related domain documentation: `docs/F02-SPATIAL-INTEGRITY.md`
- Implementation history: [PR #10](https://github.com/nestrada88/gpx-processing-pipeline/pull/10)

This file documents existing behavior only; it adds no runtime or test changes.
