# F08 — Bundled GPX/Garmin XSD provenance

Runtime validation uses these exact, local XSD bytes. No runtime network fetch is
performed. Each file is checked against a pinned Git blob SHA-1 before schema
compilation; the pin fixes the **mirrored content**, not vendor authenticity.

**Provenance limitation:** Files were fetched from the public GitHub copies
listed below; this work did not download and byte-compare them against live
Topografix/Garmin vendor hosts. The schemas carry the expected vendor
namespaces, but present-day vendor byte identity remains unverified.

| Bundled file | Mirror repository path | Published vendor reference |
|---|---|---|
| `gpx.xsd` | `jpickup/GarminTools/gpx/src/main/resources/xsd/gpx.xsd` | https://www.topografix.com/GPX/1/1/gpx.xsd |
| `GpxExtensionsv3.xsd` | `logiqx/gpx-ideas/docs/garmin/GpxExtensionsv3.xsd` | https://www8.garmin.com/xmlschemas/GpxExtensionsv3.xsd |
| `TrackPointExtensionv1.xsd` | `logiqx/gpx-ideas/docs/garmin/TrackPointExtensionv1.xsd` | https://www8.garmin.com/xmlschemas/TrackPointExtensionv1.xsd |
| `TrackPointExtensionv2.xsd` | `logiqx/gpx-ideas/docs/garmin/TrackPointExtensionv2.xsd` | https://www8.garmin.com/xmlschemas/TrackPointExtensionv2.xsd |
| `WaypointExtensionv1.xsd` | `logiqx/gpx-ideas/docs/garmin/WaypointExtensionv1.xsd` | https://www8.garmin.com/xmlschemas/WaypointExtensionv1.xsd |
| `TripExtensionsv1.xsd` | `logiqx/gpx-ideas/docs/garmin/TripExtensionsv1.xsd` | https://www8.garmin.com/xmlschemas/TripExtensionsv1.xsd |
| `PressureExtensionv1.xsd` | `logiqx/gpx-ideas/docs/garmin/PressureExtensionv1.xsd` | https://www8.garmin.com/xmlschemas/PressureExtensionv1.xsd |
| `PowerExtensionv1.xsd` | `logiqx/gpx-ideas/docs/garmin/PowerExtensionv1.xsd` | https://www8.garmin.com/xmlschemas/PowerExtensionv1.xsd |
| `AdventuresExtensionv1.xsd` | `logiqx/gpx-ideas/docs/garmin/AdventuresExtensionv1.xsd` | https://www8.garmin.com/xmlschemas/AdventuresExtensionv1.xsd |

Pinned Git blob checksums are stored in
`src/gpx_pipeline/production_schemas.py` and verified on every validation
invocation. Replacing a bundled schema must update its checksum and test
fixtures together. No separate status or approval process is implied.

## Current scope
- GPX 1.1 XSD structure and Garmin extension root-element XSD.
- Unknown extension namespaces fail closed.
- No implicit schema imports/includes, remote fetching, or external entities.
- Source GPX bytes are unchanged.
- Device transfer, Garmin course conversion and alert behavior remain unverified.
- The legacy F01 extension-schema implementation validates descendants
  independently and is not equivalent to F08's root-aware validation.
