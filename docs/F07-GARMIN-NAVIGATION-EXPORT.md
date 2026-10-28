# F07 — Garmin Navigation Export

## Responsibility

F07 produces conservative, device-labeled GPX 1.1 navigation files and independently audits their offline integrity and transfer-workflow constraints. **GPX generation, offline software validation, Garmin application import, and physical-device verification are distinct operations.** A file accepted by the exporter is not evidence of successful import, on-device course fidelity, off-course alerts, waypoint guidance or independent offline navigation.

Source implementations: [Garmin export](../src/gpx_pipeline/garmin_export.py) and [compatibility verification](../src/gpx_pipeline/garmin_compatibility.py). Implementation history: [PR #18](https://github.com/nestrada88/gpx-processing-pipeline/pull/18), [PR #19](https://github.com/nestrada88/gpx-processing-pipeline/pull/19).

## Technical references

- [Navigation export](f07/navigation-export.md): targets, GPX preservation, exact geometry audit, checkpoint manifest, XSD options and export failures.
- [Compatibility verification](f07/compatibility-verification.md): independent integrity verification, canonicalized waypoint XML, import modes, local schema evidence and software status.

## Device targets and workflow distinction

| Target | Device ID | Export-labeled transfer path | Profile device-waypoint limit |
| --- | --- | --- | --- |
| Garmin eTrex SE | `etrex-se` | Garmin Explore: GPX import to course | 1,000 |
| Garmin Instinct 2X Solar Tactical | `instinct-2x-tactical` | Garmin Connect: GPX course import | Unknown (`None`) |

The implementation's 1,000-waypoint eTrex profile check must **not** be conflated with the separate Garmin Explore **website** 500-waypoint import limit. Connect import numerical point capacities remain unverified. The compatibility verifier models Explore website import modes specifically, not all Explore mobile-app behaviors.

| Compatibility workflow | Max points per imported line | Max waypoints per website import |
| --- | ---: | ---: |
| `explore-web-tracks` | 10,000 | 500 |
| `explore-web-routes` | 200 | 500 |
| `connect-course` | Unknown | Unknown |

In Explore website modes, the selected line limit applies to imported GPX track and route lines alike. The website line constraints are *workflow* limits, not universal device storage capacities. Multi-segment track conversion under `explore-web-routes` is explicitly unverified.

## Domain invariants

1. F01 canonical GPX and F02 spatial validation precede export. Optional F05 `WaypointCatalog` must correspond to the exact source waypoint identities.
2. Source track/route coordinate **text tokens**, original point ordering, segment topology and waypoint identities are preserved. Export does not densify, simplify, reroute, invent timestamps or silently convert tracks into routes.
3. The only intentional export-tree change is the GPX root `creator` attribute. Device targeting does not imply that Garmin proprietary extensions, FIT files, turn instructions or alerts have been generated.
4. Source/export SHA-256 values and geometry fingerprints document software lineage; they do not establish Garmin software conversion or hardware interoperability.
5. Checkpoint-order annotations are stored in the external manifest, not fabricated GPX/Garmin extension elements. The exporter rejects populated GPX extensions and unregistered namespaces rather than silently stripping them.
6. Local authoritative GPX XSD configuration is required for strict schema claims. Synthetic test XSDs exercise validator wiring but do **not** prove production Topografix GPX 1.1 compliance.
7. `software_status="validated"` is an **offline software assessment**, not physical-device validation. `physical_device_verified` is `False` in the current F07 verifier.

## High-level workflow

```text
F01 canonical GPX + F02 spatial validation + optional F05 catalog
                  |
           export_garmin_navigation()
                  |
     device-labeled GPX + hash/audit + JSON manifest
                  |
            verify_garmin_export()
                  |
     offline software findings and transfer-mode limits
                  |
     [Separate Garmin application/device field evidence]
```

`export_garmin_pair()` produces two independent target-labeled results from the same canonical input. Verification requires the workflow corresponding to each device, and target-specific files must not be treated as device-tested simply because their source geometry matches.

## Cross-domain boundaries and evidence

F08 handles production GPX/Garmin schema validation, F09 owns pipeline/CLI orchestration and F10 owns operational/field validation. F07's offline verifier does not replace those responsibilities. See [F01](domains/F01-gpx-interoperability.md), [F02](F02-SPATIAL-INTEGRITY.md), [F05](F05-WAYPOINT-INTELLIGENCE.md), and [F06](F06-ANALYTICAL-PROCESSING.md).

Regression sources: [export tests](../tests/test_f07_garmin_export.py), [compatibility tests](../tests/test_f07_garmin_compatibility.py). Tests are committed but were **not re-executed** for this documentation-only change. Run `python -m pytest -q` in a configured checkout and inspect GitHub Actions results independently. Real Explore/Connect imports, on-device navigation, alert behavior and device limits require separately collected evidence.
