# NV-02 — DEM numerical and vertical-reference contract

Base: `main` commit `10b81ab55f4c81098fde2698fb7ed421580f8318`.

## Verified in automated synthetic tests

- WGS 84 geodetic coordinates transform into the raster-declared horizontal CRS with explicit longitude/latitude ordering.
- For a metric-height 2×2 synthetic raster, bilinear interpolation is checked against a separately calculated weighted sum; nearest projected lookup uses a known pixel.
- Source GPX elevation and source bytes remain unchanged. DEM-derived elevation is stored in an independent field.
- `vertical_datum=None` means unknown, not equivalent to the GPX elevation reference.
- Both F03 sampling entrypoints reject empty or whitespace-only declared datum metadata.

## Scientific and implementation boundary

`DEMProvenance.vertical_datum` is a **caller assertion**, not independently authenticated raster metadata. F03 performs **horizontal coordinate transformation only**. It does not compute geoid separation or vertical conversions and does not establish the reference of recorded GPX `<ele>` values.

Within one DEM in a single calculation, finite metre heights can be used for **relative derived elevation differences**, with caveats for DEM quality and changing vertical offsets. Combining absolute heights from distinct reference systems is not verified and must not be silently treated as commensurate. A supplied datum label must not be taken as proof that a vertical transformation happened.

If future code combines DEM heights with independently sourced absolute elevations, it must require an explicit compatibility predicate or a traceable supported vertical transformation, and reject incompatible references. Existing analytics deliberately retain source elevations separately, so this change does not invent a reference for recorded heights or force unavailable DEM inputs to fail.

## Test and failure contract

```sh
python -m pytest -q tests/test_nv02_dem_reference_contracts.py
python -m pytest -q
```

The reference fixtures and domain tests check software arithmetic and metadata integrity. They do not demonstrate source DEM accuracy or any physical Garmin navigation capability. P0 field validation remains on hold.

## Follow-on risk for NV-03/NV-05

- Quantify ascent/descent sensitivity to raster noise and sampling interval.
- Track datum and uncertainty semantics through terrain profile, route-analysis and forecast outputs.
- Verify missing datum remains explicit wherever absolute elevations are compared.
