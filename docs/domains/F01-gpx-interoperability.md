# F01 — GPX Interoperability

## Purpose

Provide secure GPX 1.1 ingestion, standards-based structural validation, canonical representation, and serialization without unintended semantic data loss.

## Responsibilities

- Secure, resource-bounded XML parsing and namespace identification.
- Topografix GPX 1.1 structural validation.
- Recognition and configured validation of registered Garmin XML extensions.
- Canonical representation of metadata, waypoints, routes, tracks, segments, points, and extensions.
- Source geometry, point ordering, and segment preservation.
- Deterministic GPX 1.1 serialization and parse–serialize–parse equivalence checks.
- Explicit diagnostics and unsupported-extension policy.

## Exclusions

Spatial and temporal plausibility, DEM enrichment, route optimization, activity forecasting, and device-specific Garmin export adaptation are downstream responsibilities.

## Verification targets

XML security; valid/invalid GPX structure; Garmin extension handling; geometry and metadata preservation; unknown extensions; deterministic serialization; semantic round-trip equivalence.

## Implementation status

Scope recorded; functionality and automated tests are not yet implemented.
